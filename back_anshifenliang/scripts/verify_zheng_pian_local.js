/**
 * 校验整篇职事信息本地读取（短文件名 + 映射表）
 */
const path = require('path');
const { loadValueToKeyMap, readLocalZhengPian } = require('../lib/zheng_pian_local');

const DATA_DIR = process.env.DATA_DIR || path.resolve(__dirname, '../data');

const SPOT_CHECKS = [
  '李常受文集一九八一年第一册，完成神新约的经纶，顾到保罗完成职事和约翰修补职事的中心异象，在基督身体的行动中移民并建立召会，以及等待我们主耶稣基督的显现，第一章',
  '李常受文集一九五三年第三册，生命的认识，第一章',
  '李常受文集一九五三年第三册，生命的认识，第一章_何谓生命',
  '路加福音生命读经，第三篇',
];

function main() {
  const valueToKey = loadValueToKeyMap(DATA_DIR);
  let ok = 0;
  const errors = [];

  for (const [value, key] of [...valueToKey.entries()]) {
    const html = readLocalZhengPian(value, DATA_DIR, valueToKey);
    if (!html || html.length < 20) {
      errors.push(`读取失败: ${value}`);
      continue;
    }
    ok += 1;
  }

  console.log(`全量读取: ${ok}/${valueToKey.size}`);

  for (const title of SPOT_CHECKS) {
    const html = readLocalZhengPian(title, DATA_DIR, valueToKey);
    const status = html && html.length > 20 ? 'OK' : 'FAIL';
    console.log(`[${status}] ${title.slice(0, 48)}...`);
    if (status === 'FAIL') errors.push(`抽检失败: ${title}`);
  }

  if (errors.length) {
    console.error(`\n失败 ${errors.length} 条`);
    errors.slice(0, 10).forEach((e) => console.error(' -', e));
    process.exit(1);
  }

  console.log('\n✅ 整篇本地读取验证通过');
}

main();
