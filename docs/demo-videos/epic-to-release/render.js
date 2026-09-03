#!/usr/bin/env node
/* Render index.html to renders/epic-to-release.mp4.
 *
 * Authoring tooling, not demo runtime (same standing as demo/render_pdf.py):
 * uses puppeteer-core against the locally cached chrome-headless-shell and
 * ffmpeg, steps window.SEEK(t) deterministically, one screenshot per frame.
 *
 *   node render.js [--fps 30] [--scale 1]
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");
const puppeteer = require("puppeteer-core");

const FPS = Number(process.argv.includes("--fps") ? process.argv[process.argv.indexOf("--fps") + 1] : 30);
const HERE = __dirname;
const PAGE = "file://" + path.join(HERE, "index.html");
const OUT = path.join(HERE, "renders", "epic-to-release.mp4");

function findShell() {
  const base = path.join(os.homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  for (const v of fs.readdirSync(base)) {
    const p = path.join(base, v, "chrome-headless-shell-mac-arm64", "chrome-headless-shell");
    if (fs.existsSync(p)) return p;
  }
  throw new Error("no cached chrome-headless-shell under " + base);
}

(async () => {
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "s7-video-frames-"));
  const browser = await puppeteer.launch({
    executablePath: findShell(),
    headless: "shell",
    args: ["--no-sandbox", "--force-device-scale-factor=1", "--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(PAGE, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);

  const duration = await page.evaluate(() => window.DURATION);
  const total = Math.round(duration * FPS);
  console.log(`rendering ${total} frames @ ${FPS}fps (${duration}s)`);

  const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    await page.evaluate((t) => window.SEEK(t), f / FPS);
    await page.screenshot({
      path: path.join(frames, `f${String(f).padStart(5, "0")}.jpg`),
      type: "jpeg",
      quality: 92,
    });
    if (f % 300 === 0) {
      const rate = (f + 1) / ((Date.now() - t0) / 1000);
      console.log(`  frame ${f}/${total}  (${rate.toFixed(1)} fps render rate)`);
    }
  }
  await browser.close();

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const ff = spawnSync("ffmpeg", [
    "-y", "-framerate", String(FPS),
    "-i", path.join(frames, "f%05d.jpg"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "medium",
    "-movflags", "+faststart",
    OUT,
  ], { stdio: ["ignore", "inherit", "inherit"] });
  if (ff.status !== 0) throw new Error("ffmpeg failed");
  fs.rmSync(frames, { recursive: true, force: true });
  console.log("done:", OUT, (fs.statSync(OUT).size / 1e6).toFixed(1) + " MB");
})();
