import { chromium } from 'playwright';

const url = 'http://localhost/#/zh2tw-practice';
const cases = [
  {
    name: 'no-error',
    input: '根据圣经，祭司职分有三面',
    out: 'D:/copypan/testC/zh2tw/screenshot-review-no-error.png',
  },
  {
    name: 'has-error',
    input: '教会每周聚会，台湾的弟兄姐妹',
    out: 'D:/copypan/testC/zh2tw/screenshot-review-has-error.png',
  },
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1000, height: 1200 } });

for (const c of cases) {
  await page.goto(url + '?_=' + Date.now(), { waitUntil: 'networkidle', timeout: 60000 });
  await page.fill('textarea', c.input);
  await page.getByRole('button', { name: '转换' }).click();
  await page.waitForTimeout(4000);
  const status = await page.locator('.review-header').innerText().catch(() => '');
  console.log(c.name + ':', status.trim().replace(/\s+/g, ' '));
  await page.screenshot({ path: c.out, fullPage: true });
  console.log('saved:', c.out);
}

await browser.close();
