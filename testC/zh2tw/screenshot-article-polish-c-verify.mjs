import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const base = 'http://localhost:5174/#/article-polish-c';
const outDir = 'D:/copypan/front_mic/frontend';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto(base, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);

const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const pageBg = await page.evaluate(() => {
  const el = document.querySelector('.page');
  return el ? getComputedStyle(el).backgroundColor : null;
});
await page.screenshot({ path: `${outDir}/verify-1-page-bg.png`, fullPage: false });

await page.getByText('体现主恢复色彩').click();
await page.waitForTimeout(500);
const ministryActive = await page.evaluate(() => {
  const el = document.querySelector('.ministry-tag.active');
  if (!el) return null;
  const s = getComputedStyle(el);
  return { background: s.backgroundColor, border: s.borderColor, color: s.color };
});
await page.screenshot({ path: `${outDir}/verify-2-ministry-green.png`, fullPage: false });

await page.getByRole('button', { name: '恩典陵园' }).click();
await page.waitForTimeout(800);
const firstRole = page.locator('.role-card').first();
await firstRole.click();
await page.waitForTimeout(500);
const roleActive = await page.evaluate(() => {
  const el = document.querySelector('.role-card.active');
  if (!el) return null;
  const s = getComputedStyle(el);
  return {
    borderLeft: s.borderLeft,
    borderLeftWidth: s.borderLeftWidth,
    borderLeftColor: s.borderLeftColor,
    background: s.backgroundColor,
  };
});
await page.screenshot({ path: `${outDir}/verify-3-role-active.png`, fullPage: false });

const report = { bodyBg, pageBg, ministryActive, roleActive };
writeFileSync(`${outDir}/verify-style-report.json`, JSON.stringify(report, null, 2), 'utf-8');
console.log(JSON.stringify(report, null, 2));
await browser.close();
