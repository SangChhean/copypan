import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const url = 'http://localhost:5174/#/article-polish-c';
const out = 'D:/copypan/front_mic/frontend/article-polish-c-screenshot.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2500);

const report = {
  url,
  title: await page.title(),
  bodyPreview: (await page.locator('body').innerText()).slice(0, 600),
  consoleErrors: [],
};

page.on('console', (msg) => {
  if (msg.type() === 'error') report.consoleErrors.push(msg.text());
});

await page.screenshot({ path: out, fullPage: true });
writeFileSync('D:/copypan/front_mic/frontend/article-polish-c-screenshot-report.json', JSON.stringify(report, null, 2), 'utf-8');
console.log(JSON.stringify(report, null, 2));
console.log('screenshot:', out);
await browser.close();
