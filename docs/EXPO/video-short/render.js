#!/usr/bin/env node
/* Render this composition to renders/<dir-name>.mp4.
 *
 * Authoring tooling, not demo runtime (same standing as demo/render_pdf.py):
 * puppeteer-core against the locally cached chrome-headless-shell plus ffmpeg,
 * stepping window.SEEK(t) frame by frame, one screenshot per frame.
 *
 * The project is served over a loopback HTTP server rather than file:// so the
 * runtime's fetch() of compositions/*.html and the @font-face woff2 both load
 * under a normal origin. Nothing leaves 127.0.0.1 and nothing is fetched from
 * the network — gsap and the font are vendored in vendor/.
 *
 *   NODE_PATH=<modules> node render.js [--fps 30] [--start 0] [--end N]
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const { spawnSync } = require("child_process");
const puppeteer = require("puppeteer-core");

const HERE = __dirname;
const NAME = path.basename(HERE);

function arg(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i === -1 ? fallback : Number(process.argv[i + 1]);
}
function argStr(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i === -1 ? fallback : process.argv[i + 1];
}
const FPS = arg("--fps", 30);

/* Each film is rendered twice: once clean, to present over, and once with the
   word-synced caption overlay, which becomes the narrated cut. ffmpeg here has
   no libass, so captions cannot be burned in afterwards — they have to come
   from the page. The flag rides in on the query string; the static server
   already drops the query when resolving a path, and reading it is
   deterministic, so frame output stays reproducible. */
const CAPTIONS = arg("--captions", 1);
const OUT = path.join(HERE, "renders", argStr("--out", NAME) + ".mp4");

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".svg": "image/svg+xml",
};

function findShell() {
  const base = path.join(os.homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  for (const v of fs.readdirSync(base)) {
    for (const plat of ["mac-arm64", "mac-x64", "linux-x64"]) {
      const p = path.join(base, v, "chrome-headless-shell-" + plat, "chrome-headless-shell");
      if (fs.existsSync(p)) return p;
    }
  }
  throw new Error("no cached chrome-headless-shell under " + base);
}

function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "") || "index.html";
      const file = path.join(HERE, rel);
      if (!file.startsWith(HERE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404).end("not found");
        return;
      }
      res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

(async () => {
  const server = await serve();
  const port = server.address().port;
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "s7-expo-frames-"));

  const browser = await puppeteer.launch({
    executablePath: findShell(),
    headless: "shell",
    args: ["--no-sandbox", "--force-device-scale-factor=1", "--hide-scrollbars"],
  });
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("PAGE ERROR:", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.error("CONSOLE:", m.text()); });
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(`http://127.0.0.1:${port}/index.html?captions=${CAPTIONS}`, { waitUntil: "networkidle0" });
  await page.evaluate(() => window.__hfBoot);
  await page.evaluate(() => document.fonts.ready);

  const duration = await page.evaluate(() => window.DURATION);
  if (!duration || !isFinite(duration)) throw new Error("composition reported no DURATION");
  const from = arg("--start", 0);
  const to = arg("--end", duration);
  const first = Math.round(from * FPS);
  const total = Math.round(to * FPS);
  console.log(`rendering frames ${first}..${total} @ ${FPS}fps (${duration}s composition)`);

  const t0 = Date.now();
  for (let f = first; f < total; f++) {
    await page.evaluate((t) => window.SEEK(t), f / FPS);
    await page.screenshot({
      path: path.join(frames, `f${String(f - first).padStart(5, "0")}.jpg`),
      type: "jpeg",
      quality: 92,
    });
    if ((f - first) % 300 === 0 && f > first) {
      const rate = (f - first) / ((Date.now() - t0) / 1000);
      console.log(`  frame ${f}/${total}  (${rate.toFixed(1)} fps render rate)`);
    }
  }
  await browser.close();
  server.close();

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
})().catch((e) => { console.error(e); process.exit(1); });
