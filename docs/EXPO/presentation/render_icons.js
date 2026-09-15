#!/usr/bin/env node
/* Render the film's icon set to PNGs for the decks, one per (icon, accent).
 *
 * Authoring tooling. Keeps the slides and the films on the same icon
 * language without hand-drawing shapes in python-pptx. Offline: the icon
 * paths come from ../video-short/icons.js, nothing is fetched.
 *
 *   NODE_PATH=<modules> node render_icons.js
 */
"use strict";
const fs = require("fs"), os = require("os"), path = require("path");
const puppeteer = require("puppeteer-core");

const HERE = __dirname;
const OUT = path.join(HERE, "icons");
const ACCENTS = {
  red: "#d8232a", teal: "#0f7a6c", amber: "#b0770c", violet: "#6b4fa8",
  blue: "#1d5c7a", green: "#1f7a4d", slate: "#4c5560",
};

function findShell() {
  const b = path.join(os.homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  for (const v of fs.readdirSync(b))
    for (const p of ["mac-arm64", "mac-x64", "linux-x64"]) {
      const q = path.join(b, v, "chrome-headless-shell-" + p, "chrome-headless-shell");
      if (fs.existsSync(q)) return q;
    }
  throw new Error("no cached chrome-headless-shell");
}

(async () => {
  const src = fs.readFileSync(path.join(HERE, "..", "video-short", "icons.js"), "utf8");
  const sandbox = { window: {} };
  new Function("window", src)(sandbox.window);
  const ICONS = sandbox.window.ICONS;

  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: findShell(), headless: "shell",
    args: ["--no-sandbox", "--force-device-scale-factor=1"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 160, height: 160, deviceScaleFactor: 1 });

  let n = 0;
  for (const name of ICONS.names) {
    for (const [accent, hex] of Object.entries(ACCENTS)) {
      const html = `<html><body style="margin:0;width:160px;height:160px">
        <div style="width:160px;height:160px;display:flex;align-items:center;justify-content:center;color:${hex}">
          <div style="width:112px;height:112px">${ICONS(name, { w: 1.7 })}</div>
        </div></body></html>`;
      await page.setContent(html, { waitUntil: "load" });
      await page.evaluate(() => { document.querySelector("svg").style.width = "112px";
                                  document.querySelector("svg").style.height = "112px"; });
      await page.screenshot({ path: path.join(OUT, `${name}-${accent}.png`), omitBackground: true });
      n++;
    }
  }
  await browser.close();
  console.log(`wrote ${n} icon PNGs to ${OUT}`);
})().catch((e) => { console.error(e); process.exit(1); });
