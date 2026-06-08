import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const url = 'http://localhost:5174/#/practice-translate';
const out = 'D:/copypan/front_mic/frontend/practice-translate-screenshot.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2000);

const report = {
  bodyBg: await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  containerBg: await page.evaluate(() => {
    const el = document.querySelector('.container');
    return el ? getComputedStyle(el).backgroundColor : null;
  }),
  activeBtn: await page.evaluate(() => {
    const el = document.querySelector('.toggle-btn.active');
    if (!el) return null;
    const s = getComputedStyle(el);
    return { background: s.backgroundColor, color: s.color };
  }),
  toggleContainer: await page.evaluate(() => {
    const el = document.querySelector('.direction-toggle');
    if (!el) return null;
    const s = getComputedStyle(el);
    return { background: s.backgroundColor, borderRadius: s.borderRadius };
  }),
  translateBtn: await page.evaluate(() => {
    const el = document.querySelector('.translate-btn');
    if (!el) return null;
    return getComputedStyle(el).backgroundColor;
  }),
};

await page.screenshot({ path: out, fullPage: true });
writeFileSync('D:/copypan/front_mic/frontend/practice-translate-screenshot-report.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
console.log('screenshot:', out);
await browser.close();
