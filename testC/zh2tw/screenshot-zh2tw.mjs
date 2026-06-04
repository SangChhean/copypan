import { chromium } from 'playwright';

const url = 'http://localhost/zh2tw/';
const text = '教会每周聚会，台湾的弟兄姐妹一起读经，略过困难的地方';
const out = 'D:/copypan/testC/zh2tw/zh2tw-test-screenshot.png';

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 960, height: 1100 },
  extraHTTPHeaders: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' },
});
const page = await context.newPage();
await page.goto(url + '?t=' + Date.now(), { waitUntil: 'networkidle', timeout: 60000 });
await page.fill('textarea', text);
await page.getByRole('button', { name: '转换' }).click();
await page.waitForTimeout(4000);

const report = {
  url,
  resultText: await page.locator('.result-text').first().innerText().catch(() => ''),
  errorCharCount: await page.locator('.error-char').count(),
  candidateBtnCount: await page.locator('.btn-candidate').count(),
  errorMsg: (await page.locator('p.error').allInnerTexts()).join(' | '),
};

await page.screenshot({ path: out, fullPage: true });
console.log(JSON.stringify(report, null, 2));
console.log('screenshot:', out);
await browser.close();
