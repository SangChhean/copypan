import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const url = 'http://localhost:5174/#/zh2tw-practice';
const out = 'D:/copypan/front_mic/frontend/zh2tw-practice-screenshot.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2000);

const report = {
  bodyBg: await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  titleColor: await page.evaluate(() => {
    const el = document.querySelector('.title');
    return el ? getComputedStyle(el).color : null;
  }),
  activeBtn: await page.evaluate(() => {
    const el = document.querySelector('.btn-dir.active');
    if (!el) return null;
    const s = getComputedStyle(el);
    return { background: s.backgroundColor, color: s.color };
  }),
  directionRow: await page.evaluate(() => {
    const el = document.querySelector('.direction-row');
    if (!el) return null;
    return getComputedStyle(el).backgroundColor;
  }),
  primaryBtn: await page.evaluate(() => {
    const el = document.querySelector('.btn-primary');
    return el ? getComputedStyle(el).backgroundColor : null;
  }),
};

await page.screenshot({ path: out, fullPage: true });
writeFileSync('D:/copypan/front_mic/frontend/zh2tw-practice-screenshot-report.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
console.log('screenshot:', out);
await browser.close();
