/* Flat stroke icon set for the expo films.
 *
 * Inline SVG strings, 24x24, currentColor, round caps — so an icon inherits
 * the accent colour of the tile it sits in and scales without assets. No
 * network, no sprite file: hard rule 4 applies to authoring tooling too.
 */
"use strict";

window.ICONS = (function () {
  var P = {
    doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    dev: '<circle cx="12" cy="8" r="3.4"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    bot: '<rect x="4" y="8" width="16" height="11" rx="3"/><path d="M12 4.5V8"/><circle cx="12" cy="3.4" r="1.3"/><path d="M9 13v1.6M15 13v1.6"/>',
    branch: '<circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="9" r="2.2"/><path d="M6 7.2v9.6"/><path d="M18 11.2c0 3.2-3 4-6 4.4"/>',
    check: '<path d="M4.5 12.5l5 5 10-11"/>',
    cross: '<path d="M6 6l12 12M18 6L6 18"/>',
    lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.4"/><path d="M8.2 10.5V7.6a3.8 3.8 0 0 1 7.6 0v2.9"/>',
    flask: '<path d="M9.5 3v6.2L4.8 17.6A2.2 2.2 0 0 0 6.7 21h10.6a2.2 2.2 0 0 0 1.9-3.4L14.5 9.2V3"/><path d="M8.4 3h7.2"/><path d="M7.6 14.6h8.8"/>',
    chart: '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16.5v-4M12.5 16.5V8M17 16.5v-6.5"/>',
    alert: '<path d="M12 4.2 2.9 19.3a1.4 1.4 0 0 0 1.2 2.1h15.8a1.4 1.4 0 0 0 1.2-2.1z"/><path d="M12 10v4.2M12 17.6h.01"/>',
    arrow: '<path d="M4 12h15"/><path d="M13.5 6.5 19.5 12l-6 5.5"/>',
    folder: '<path d="M3.5 6.6A2.1 2.1 0 0 1 5.6 4.5h3.3l2.1 2.6h7.4a2.1 2.1 0 0 1 2.1 2.1v8.3a2.1 2.1 0 0 1-2.1 2.1H5.6a2.1 2.1 0 0 1-2.1-2.1z"/>',
    code: '<path d="M8.5 8 4 12.2l4.5 4.2"/><path d="M15.5 8 20 12.2l-4.5 4.2"/><path d="M13.6 5.2 10.4 19"/>',
    db: '<ellipse cx="12" cy="6" rx="7.4" ry="2.9"/><path d="M4.6 6v12c0 1.6 3.3 2.9 7.4 2.9s7.4-1.3 7.4-2.9V6"/><path d="M4.6 12c0 1.6 3.3 2.9 7.4 2.9s7.4-1.3 7.4-2.9"/>',
    shield: '<path d="M12 3 5 6v5.6c0 4.3 2.9 8.1 7 9.4 4.1-1.3 7-5.1 7-9.4V6z"/><path d="M9.2 12.2 11.3 14.3 15 10.4"/>',
    eye: '<path d="M2.6 12S6.3 5.6 12 5.6 21.4 12 21.4 12 17.7 18.4 12 18.4 2.6 12 2.6 12"/><circle cx="12" cy="12" r="2.9"/>',
    rocket: '<path d="M12 2.8c3.3 2.3 5.2 5.9 5.2 9.8l-2.4 2.7H9.2l-2.4-2.7c0-3.9 1.9-7.5 5.2-9.8"/><circle cx="12" cy="10" r="2"/><path d="M9.2 15.3 7 20l3.4-1.4M14.8 15.3 17 20l-3.4-1.4"/>',
    layers: '<path d="M12 3 3 7.8l9 4.8 9-4.8z"/><path d="M3 12.6 12 17.4l9-4.8"/><path d="M3 16.9 12 21.7l9-4.8"/>',
    clock: '<circle cx="12" cy="12" r="8.6"/><path d="M12 7.2V12l3.3 2"/>',
    puzzle: '<path d="M10.2 4.4a1.9 1.9 0 0 1 3.6 0v1.4h2.6a1.5 1.5 0 0 1 1.5 1.5v2.5h-1.4a1.9 1.9 0 0 0 0 3.7h1.4v2.6a1.5 1.5 0 0 1-1.5 1.5h-2.6v-1.4a1.9 1.9 0 0 0-3.6 0v1.4H7.5A1.5 1.5 0 0 1 6 16.1v-2.6H7.4a1.9 1.9 0 0 0 0-3.7H6V7.3a1.5 1.5 0 0 1 1.5-1.5h2.7z"/>',
    question: '<circle cx="12" cy="12" r="8.6"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.7"/><path d="M12 17.4h.01"/>',
    people: '<circle cx="9" cy="8.4" r="3"/><path d="M2.8 19.4a6.2 6.2 0 0 1 12.4 0"/><path d="M16.4 6.1a3 3 0 0 1 0 5.8"/><path d="M17.6 14.2a6.2 6.2 0 0 1 3.6 5.2"/>',
    split: '<path d="M4 6h4l4 6 4-6h4"/><path d="M4 18h4l4-6"/><path d="M16.8 3.4 20.4 6l-3.6 2.6"/><path d="M16.8 15.4 20.4 18l-3.6 2.6"/>',
    merge: '<path d="M20 12H4"/><path d="M9.8 6.2 4 12l5.8 5.8"/><path d="M14 4.5c0 4 2 7.5 6 7.5"/><path d="M14 19.5c0-4 2-7.5 6-7.5"/>',
  };
  function svg(name, opts) {
    var d = P[name];
    if (!d) throw new Error("unknown icon: " + name);
    opts = opts || {};
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="' + (opts.w || 1.8) + '" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + d + "</svg>";
  }
  svg.names = Object.keys(P);
  return svg;
})();
