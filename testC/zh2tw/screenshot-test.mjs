import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const url = 'http://localhost/#/zh2tw-practice';
const text = '教会每周聚会，台湾的弟兄姐妹一起读经，略过困难的地方';
const out = 'D:/copypan/testC/zh2tw/zh2tw-practice-screenshot.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 960, height: 1000 } });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.fill('textarea', text);
await page.getByRole('button', { name: '转换' }).click();
await page.waitForTimeout(4000);

const report = {
  resultText: await page.locator('.result-text').first().innerText().catch(() => ''),
  errorCharCount: await page.locator('.error-char').count(),
  candidateBtnCount: await page.locator('.btn-candidate').count(),
  errorMsg: await page.locator('p.error').first().innerText().catch(() => ''),
};

await page.screenshot({ path: out, fullPage: true });
writeFileSync('D:/copypan/testC/zh2tw/screenshot-report.json', JSON.stringify(report, null, 2), 'utf-8');
console.log(JSON.stringify(report, null, 2));
console.log('screenshot:', out);
await browser.close();
