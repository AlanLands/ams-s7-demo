/* HyperFrames-compatible composition runtime — authoring tooling, not demo
 * runtime (same standing as demo/render_pdf.py and the render.js scripts
 * under docs/demo-videos).
 *
 * Implements the framework contract the composition files rely on:
 *   - window.__timelines registry, created before any composition script runs
 *   - data-composition-src loading from external <template> files
 *   - automatic nesting of sub-timelines into their parent by data-start
 *   - clip mount/unmount from data-start + data-duration
 *   - relative timing: data-start="<id>", "<id> + n", "<id> - n"
 * and exposes window.SEEK(t) / window.DURATION for the frame-stepping renderer.
 *
 * Fully deterministic: no randomness, no wall-clock reads on the render path.
 */
"use strict";

window.__timelines = {};

(function () {
  var EPS = 1e-6;
  var clips = [];   /* {el, absStart, duration} — mount/unmount set */
  var master = null;

  /* ---- relative timing ------------------------------------------------ */

  function durationOf(el) {
    var d = el.getAttribute("data-duration");
    if (d !== null && d !== "") return parseFloat(d);
    if (el.tagName === "VIDEO" || el.tagName === "AUDIO") {
      return isFinite(el.duration) ? el.duration : 0;
    }
    return 0;
  }

  /* Resolve data-start within the clip's own parent composition. Accepts
     absolute seconds, or "<id>", "<id> + n", "<id> - n" meaning "when that
     clip ends". Cycles raise rather than silently resolving to 0. */
  function resolveStart(el, scope, seen) {
    var raw = (el.getAttribute("data-start") || "0").trim();
    if (raw === "") return 0;
    var n = Number(raw);
    if (!isNaN(n)) return n;

    var m = /^([A-Za-z0-9_\-:.]+)\s*(?:([+-])\s*([0-9.]+))?$/.exec(raw);
    if (!m) throw new Error("unparseable data-start " + JSON.stringify(raw) + " on #" + el.id);

    var refId = m[1];
    var offset = m[2] ? (m[2] === "+" ? 1 : -1) * parseFloat(m[3]) : 0;

    seen = seen || {};
    if (seen[refId]) throw new Error("circular data-start reference at " + refId);
    seen[refId] = true;

    var ref = scope.querySelector('[id="' + refId + '"]');
    if (!ref) throw new Error("data-start references unknown clip " + refId + " (from #" + el.id + ")");
    return resolveStart(ref, scope, seen) + durationOf(ref) + offset;
  }

  function parentComposition(el) {
    var p = el.parentElement;
    while (p) {
      if (p.hasAttribute && p.hasAttribute("data-composition-id")) return p;
      p = p.parentElement;
    }
    return null;
  }

  /* ---- composition loading -------------------------------------------- */

  function loadComposition(el) {
    var src = el.getAttribute("data-composition-src");
    if (!src) return Promise.resolve([]);
    return fetch(src)
      .then(function (r) {
        if (!r.ok) throw new Error("composition fetch failed: " + src + " (" + r.status + ")");
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var tpl = doc.querySelector("template");
        if (!tpl) throw new Error("composition file has no <template>: " + src);
        var frag = tpl.content.cloneNode(true);

        /* Scripts must run after the nodes are in the document and after any
           nested compositions below them have mounted, so pull them aside. */
        var scripts = Array.prototype.slice.call(frag.querySelectorAll("script"));
        scripts.forEach(function (s) { s.parentNode.removeChild(s); });

        el.appendChild(frag);
        return loadAll(el).then(function (inner) {
          return inner.concat(scripts.map(function (s) { return s.textContent; }));
        });
      });
  }

  function loadAll(root) {
    var pending = Array.prototype.slice
      .call(root.querySelectorAll("[data-composition-src]"))
      .filter(function (el) { return !el.__hfLoaded; });
    pending.forEach(function (el) { el.__hfLoaded = true; });
    if (!pending.length) return Promise.resolve([]);
    return Promise.all(pending.map(loadComposition)).then(function (lists) {
      return lists.reduce(function (a, b) { return a.concat(b); }, []);
    });
  }

  /* ---- timeline assembly ---------------------------------------------- */

  function collectClips(comp, compAbsStart) {
    /* Direct timed children of this composition (not those of nested ones). */
    var all = comp.querySelectorAll("[data-start]");
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (parentComposition(el) !== comp) continue;
      var start = compAbsStart + resolveStart(el, comp);
      clips.push({ el: el, start: start, end: start + durationOf(el) });
      if (el.hasAttribute("data-composition-id")) collectClips(el, start);
    }
  }

  function nestTimelines(comp, parentTL) {
    var all = comp.querySelectorAll("[data-composition-id]");
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (parentComposition(el) !== comp) continue;
      var id = el.getAttribute("data-composition-id");
      var tl = window.__timelines[id];
      var start = resolveStart(el, comp);
      /* The template root mounted inside carries the same composition id as
         its mount point, so guard against adding a timeline to itself. */
      if (tl && tl !== parentTL) {
        parentTL.add(tl, start);
        tl.paused(false); /* a child added while paused never renders */
      }
      /* The template root nested one level inside carries the same id; its
         own children are reached through it. */
      nestTimelines(el, tl || parentTL);
    }
  }

  /* ---- mount / unmount ------------------------------------------------ */

  function applyMounts(t) {
    for (var i = 0; i < clips.length; i++) {
      var c = clips[i];
      var on = t >= c.start - EPS && t < c.end - EPS;
      var want = on ? "" : "none";
      if (c.el.style.display !== want) c.el.style.display = want;
    }
  }

  /* ---- boot ------------------------------------------------------------ */

  function boot() {
    var root = document.querySelector("[data-composition-id][data-width]");
    if (!root) throw new Error("no top-level composition found");

    return loadAll(root).then(function (scriptBodies) {
      /* Composition scripts run innermost-first, so a parent can rely on its
         children already being registered in window.__timelines. */
      scriptBodies.forEach(function (body) {
        var s = document.createElement("script");
        s.textContent = body;
        document.body.appendChild(s);
      });

      var rootId = root.getAttribute("data-composition-id");
      master = window.__timelines[rootId];
      if (!master) throw new Error("top-level composition registered no timeline: " + rootId);

      nestTimelines(root, master);
      collectClips(root, 0);

      master.pause(0);
      window.DURATION = parseFloat(root.getAttribute("data-duration"));
      window.SEEK = function (t) {
        applyMounts(t);
        master.seek(t, false);
      };
      window.SEEK(0);
      window.__hfReady = true;
      return window.DURATION;
    });
  }

  /* index.html loads this from <head>, so the top-level composition does not
     exist yet; wait for the document before looking for it. */
  window.__hfBoot = new Promise(function (resolve, reject) {
    function go() { boot().then(resolve, reject); }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
    else go();
  });
})();
