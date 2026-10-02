// Release check: makes sure the game's scripts parse and the page boots in a real browser without errors.
// Run with `node tools/check/release-check.mjs` from the repo root (needs the `playwright` package and Chromium).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import os from 'node:os';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const failures = [];
const fail = (m) => { failures.push(m); console.error('  FAIL ' + m); };

// ---------- 1. every inline script (and the service worker) parses ----------
console.log('Checking scripts parse…');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
scripts.forEach((m, i) => {
  const attrs = m[1], code = m[2];
  if (/\bsrc=/.test(attrs) || /type=["']?(application\/(ld\+)?json|text\/template)/.test(attrs)) return;
  const line = html.slice(0, m.index).split('\n').length;
  try {
    if (/type=["']?module/.test(attrs)) {
      const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hd-')), 'inline.mjs');
      fs.writeFileSync(tmp, code);
      const r = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' });
      if (r.status) throw new Error(r.stderr.trim().split('\n').slice(-3).join(' '));
    } else new vm.Script(code, { filename: `index.html:<script #${i + 1}>` });
    console.log(`  ok   inline script #${i + 1} (line ${line}, ${code.length} chars)`);
  } catch (e) { fail(`inline script #${i + 1} starting at index.html line ${line}: ${e.message}`); }
});
try { new vm.Script(fs.readFileSync(path.join(ROOT, 'sw.js'), 'utf8'), { filename: 'sw.js' }); console.log('  ok   sw.js'); }
catch (e) { fail(`sw.js: ${e.message}`); }
if (failures.length) finish();

// ---------- 2. boot the page in headless Chromium ----------
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wav': 'audio/wav', '.m4a': 'audio/mp4' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(ROOT, path.normalize(p));
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); return res.end('not found'); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}/`;

const { chromium } = await import('playwright');
const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2 });
const errors = [];
page.on('pageerror', (e) => errors.push(`uncaught: ${e.stack || e.message}`));
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console.error: ${m.text()}${m.location()?.url ? ` (${m.location().url})` : ''}`); });
page.on('response', (r) => { if (r.url().startsWith(base) && r.status() >= 400) errors.push(`HTTP ${r.status()} for ${r.url().slice(base.length - 1)}`); });
page.on('requestfailed', (r) => { if (r.url().startsWith(base)) errors.push(`request failed: ${r.url().slice(base.length - 1)} (${r.failure()?.errorText})`); });
// keep the check offline: the live backend sees nothing (online features get an empty server instead of writing
// to production), and outside hosts like Google Fonts can't fail a release with their own hiccups
const outside = [];
await page.route((u) => !u.href.startsWith(base), (route) => {
  const u = route.request().url();
  if (!outside.includes(new URL(u).host)) outside.push(new URL(u).host);
  if (/supabase\.co\//.test(u)) return route.fulfill({ status: 200, contentType: 'application/json', body: u.includes('/rpc/') ? 'null' : '[]' });
  if (/fonts\.googleapis\.com\//.test(u)) return route.fulfill({ status: 200, contentType: 'text/css', body: '' });
  return route.fulfill({ status: 204, body: '' });
});

const step = async (name, fn) => {
  const before = errors.length;
  try { await fn(); } catch (e) { errors.push(`${name}: ${e.message.split('\n')[0]}`); }
  const fresh = errors.slice(before);
  if (fresh.length) fresh.forEach((e) => fail(`[${name}] ${e}`)); else console.log(`  ok   ${name}`);
};

console.log('Booting the game in Chromium…');
await step('page loads', () => page.goto(base, { waitUntil: 'load', timeout: 60000 }));
await step('loading screen clears', () => page.waitForSelector('#loader', { state: 'detached', timeout: 30000 }));
await step('game renders', async () => {
  await page.waitForFunction(() => document.querySelector('#main')?.children.length > 0 && document.querySelector('#tabs')?.children.length > 0, null, { timeout: 15000 });
});
await step('new ranch starts', async () => {
  const start = page.locator('[data-act="welcome"]');
  if (await start.count()) { await start.first().click(); await page.waitForTimeout(800); }
});
const tabs = await page.locator('#tabs [data-act="tab"]').evaluateAll((els) => els.map((e) => e.dataset.t)).catch(() => []);
for (const t of tabs) {
  await step(`tab "${t}" opens`, async () => {
    await page.locator(`#tabs [data-act="tab"][data-t="${t}"]`).first().click();
    await page.waitForTimeout(600);
  });
}
await step('settles with no late errors', () => page.waitForTimeout(3000));

if (outside.length) console.log(`  (stubbed outside hosts: ${outside.join(', ')})`);
await browser.close();
server.close();
finish();

function finish() {
  if (failures.length) { console.error(`\nRelease check failed (${failures.length} problem${failures.length > 1 ? 's' : ''}).`); process.exit(1); }
  console.log('\nRelease check passed.');
  process.exit(0);
}
