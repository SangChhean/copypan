import { chromium } from 'playwright';

const url = 'http://localhost/#/zh2tw-practice';
const out = 'D:/copypan/testC/zh2tw/screenshot-instant-current.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1000, height: 1200 } });
await page.goto(url + '?_=' + Date.now(), { waitUntil: 'networkidle', timeout: 60000 });
await page.fill('textarea', '教会每周聚会，台湾的弟兄姐妹');
await page.getByRole('button', { name: '转换' }).click();
await page.waitForTimeout(3000);
// 点击单条候选「周」，上下文应即时显示「周」而非「週」
await page.locator('.error-item .btn-candidate').filter({ hasText: '周' }).first().click();
await page.waitForTimeout(500);
const hl = await page.locator('.error-item .hl').first().innerText();
console.log('highlight text after click 周:', hl);
await page.screenshot({ path: out, fullPage: true });
console.log('saved:', out);
await browser.close();
