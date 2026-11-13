#!/usr/bin/env node
// Exports an Organic Brief HTML deck to a 16:9 PDF (one slide per page).
// Usage: node scripts/export_brief_pdf.js organic-brief_YYYY-MM-DD.html organic-brief_YYYY-MM-DD.pdf
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const [src, out] = process.argv.slice(2);
  if (!src || !out) { console.error('usage: export_brief_pdf.js <brief.html> <brief.pdf>'); process.exit(64); }
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  await page.goto('file://' + path.resolve(src), { waitUntil: 'load' });
  await page.pdf({ path: out, width: '13.333in', height: '7.5in', printBackground: true });
  await browser.close();
  console.log(`[brief] wrote ${out}`);
})().catch((e) => { console.error(e); process.exit(1); });
