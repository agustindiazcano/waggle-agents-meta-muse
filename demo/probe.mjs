import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const require2 = createRequire('C:/projects/projects-github-agustindiazcano/waggle-viewer-capture/web/package.json');
const { chromium } = require2('playwright-core');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.wav': 'audio/wav', '.glb': 'model/gltf-binary' };
const server = createServer((req, res) => { const p = resolve(here, '.' + decodeURIComponent(new URL(req.url, 'http://x').pathname)); if (!existsSync(p)) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'content-type': types[extname(p)] || 'application/octet-stream' }); res.end(readFileSync(p)); });
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Users/agusd/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl', '--mute-audio'] });
try { const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  for (const t of process.argv.slice(2).map(Number)) { await page.goto(`http://127.0.0.1:${port}/index.html?t=${t}`); await page.waitForFunction(() => window.__demo, null, { timeout: 30000 }); console.log('asset', t, await page.evaluate(() => window.__assetsReady)); await page.waitForTimeout(1200); await page.screenshot({ path: resolve(here, `../output/probe-${t}.png`), timeout: 90000 }); }
  console.log('errors:', errs.length ? errs.join(' | ') : 'none');
} finally { await browser.close(); server.close(); }
