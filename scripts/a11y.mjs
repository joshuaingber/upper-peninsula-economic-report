#!/usr/bin/env node
/**
 * Accessibility check: run pa11y-ci over every built HTML page in docs/ against
 * WCAG 2.1 Level AA — the standard NMU (and the DOJ 2024 ADA Title II rule)
 * requires. See docs/accessibility/GUIDELINES.md.
 *
 * Usage:
 *   python build.py     # regenerate docs/ first
 *   npm install         # once, to install pa11y-ci
 *   npm run a11y
 *
 * Robust to two gotchas we hit locally:
 *   1. A space in the repo path ("Regional Report") — file:// URLs are built
 *      with pathToFileURL (properly percent-encoded) and passed via a config
 *      file, not the shell, so nothing word-splits.
 *   2. A corrupt Puppeteer-bundled Chromium — if a real Chrome/Chromium is
 *      installed (macOS or Linux), we point pa11y at it and never touch the
 *      bundled download. In CI (no system browser) we fall back to Puppeteer's
 *      own Chromium.
 */
import { readdirSync, statSync, writeFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = resolve(process.cwd());
const docs = join(root, 'docs');

function htmlFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...htmlFiles(p));
    else if (entry.endsWith('.html')) out.push(p);
  }
  return out;
}

if (!existsSync(docs)) {
  console.error('No docs/ directory. Run `python build.py` first.');
  process.exit(1);
}
const urls = htmlFiles(docs).sort().map((p) => pathToFileURL(p).href);
if (urls.length === 0) {
  console.error('No docs/**/*.html found. Run `python build.py` first.');
  process.exit(1);
}

// Prefer a real, installed browser; fall back to Puppeteer's bundled Chromium.
const chromeCandidates = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
];
const chrome = chromeCandidates.find(existsSync);

const chromeLaunchConfig = { args: ['--no-sandbox', '--disable-setuid-sandbox'] };
if (chrome) chromeLaunchConfig.executablePath = chrome;

const config = {
  defaults: { standard: 'WCAG2AA', timeout: 60000, wait: 700, chromeLaunchConfig },
  urls,
};
const configPath = join(root, '.pa11yci.runtime.json');
writeFileSync(configPath, JSON.stringify(config, null, 2));

console.log(
  `Checking ${urls.length} pages against WCAG 2.1 AA using ` +
    (chrome ? chrome : "Puppeteer's bundled Chromium"),
);

const bin = join(
  root, 'node_modules', '.bin',
  process.platform === 'win32' ? 'pa11y-ci.cmd' : 'pa11y-ci',
);
if (!existsSync(bin)) {
  console.error('pa11y-ci not found. Run `npm install` first.');
  process.exit(1);
}
const result = spawnSync(bin, ['--config', configPath], { stdio: 'inherit' });
process.exit(result.status ?? 1);
