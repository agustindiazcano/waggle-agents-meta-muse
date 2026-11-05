/** Reproducible demo capture: serve demo/, record canvas via MediaRecorder.
 * Usage: node capture.mjs <seconds> <outputFile> [width height]
 * Requires Playwright from the viewer-capture worktree node_modules (no install).
 */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const shotMode = process.argv[2] === 'shot';
const offset = shotMode ? parseFloat(process.argv[3]) : 0;
const seconds = parseFloat(shotMode ? process.argv[4] : (process.argv[2] || '5'));
const out = resolve(shotMode ? process.argv[5] : (process.argv[3] || 'proof.webm'));
const W = parseInt((shotMode ? process.argv[6] : process.argv[4]) || '1920', 10), H = parseInt((shotMode ? process.argv[7] : process.argv[5]) || '1080', 10);
const require2 = createRequire(process.env.WAGGLE_PLAYWRIGHT_PACKAGE || 'C:/projects/projects-github-agustindiazcano/waggle-viewer-capture/web/package.json');
const { chromium } = require2('playwright-core');

const withAudio = (shotMode ? process.argv[8] : process.argv[6]) === 'audio';
const types = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.wav': 'audio/wav', '.glb': 'model/gltf-binary' };
const server = createServer((req, res) => {
  const p = resolve(here, '.' + decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!existsSync(p)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': types[extname(p)] || 'application/octet-stream' });
  res.end(readFileSync(p));
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
const launchOpts = { headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl', '--mute-audio'] };
if (process.env.WAGGLE_BROWSER_EXECUTABLE) launchOpts.executablePath = process.env.WAGGLE_BROWSER_EXECUTABLE;
else if (process.env.WAGGLE_BROWSER_CHANNEL) launchOpts.channel = process.env.WAGGLE_BROWSER_CHANNEL;
else if (process.platform === 'win32') launchOpts.executablePath = 'C:/Users/agusd/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe';
const browser = await chromium.launch(launchOpts);
try {
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`http://127.0.0.1:${port}/index.html?offset=${offset}`);
  await page.waitForFunction(() => window.__demo, null, { timeout: 30000 });
  const assetState = await page.evaluate(() => window.__assetsReady);
  console.log('asset:', assetState);
  await page.evaluate((a) => { window.__withAudio = a; }, withAudio);
  await page.evaluate((o) => { window.__offsetVal = o; }, offset);
  await page.waitForTimeout(1500);
  const mime = await page.evaluate(() => {
    const cands = ['video/mp4;codecs=avc1.640028,mp4a.40.2', 'video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'];
    for (const c of cands) if (MediaRecorder.isTypeSupported(c)) return c;
    return '';
  });
  console.log('mime:', mime || '(none)');
  await page.evaluate(async (secs) => {
    let stream = document.getElementById('c').captureStream(30);
    if (window.__withAudio) {
      const ctx = new AudioContext();
      const dest = ctx.createMediaStreamDestination();
      const subs = window.__demo.SUBS;
      for (let i = 0; i < subs.length; i++) {
        const buf = await (await fetch(`narration/line-${String(i).padStart(2, '0')}.wav`)).arrayBuffer();
        const audio = await ctx.decodeAudioData(buf);
        const src = ctx.createBufferSource(); src.buffer = audio; src.connect(dest);
        const when = subs[i][0] - (window.__offsetVal || 0);
        if (when >= -audio.duration) src.start(ctx.currentTime + Math.max(0, when) + 0.1, Math.max(0, -when));
      }
      stream = new MediaStream([...stream.getVideoTracks(), ...dest.stream.getAudioTracks()]);
    }
    const mt = ['video/mp4;codecs=avc1.640028,mp4a.40.2', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find(c => MediaRecorder.isTypeSupported(c));
    const rec = new MediaRecorder(stream, { mimeType: mt, videoBitsPerSecond: 8_000_000 });
    window.__chunks = [];
    rec.ondataavailable = e => { if (e.data.size) window.__chunks.push(e.data); };
    window.__done = new Promise(r => { rec.onstop = r; });
    rec.start(1000);
    window.__rec = rec;
    setTimeout(() => rec.stop(), secs * 1000);
  }, seconds);
  await page.waitForFunction(() => window.__rec && window.__rec.state === 'inactive', null, { timeout: seconds * 1000 + 60000 });
  const b64 = await page.evaluate(async () => {
    const blob = new Blob(window.__chunks, { type: window.__chunks[0]?.type || 'video/webm' });
    const buf = await blob.arrayBuffer();
    let s = ''; const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 32768) s += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return { b64: btoa(s), type: blob.type, size: blob.size };
  });
  writeFileSync(out, Buffer.from(b64.b64, 'base64'));
  console.log('saved', out, b64.size, b64.type, 'errors:', errors.length ? errors.join(' | ') : 'none');
  // stills for visual check
  for (const t of [2, Math.min(50, seconds), Math.min(130, seconds)]) {
    await page.evaluate((tt) => window.__demo.stateAt(tt), t);
    await page.waitForTimeout(300);
    await page.screenshot({ path: resolve(here, `../output/still-${t}.png`), timeout: 90000 });
  }
} finally { await browser.close(); server.close(); }
