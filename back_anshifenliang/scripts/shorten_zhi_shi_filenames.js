/**
 * 将 zhi_shi_html 下超长 JSON 文件名缩短为 ID 短名，并生成 filename_map.json
 *
 * 用法:
 *   node scripts/shorten_zhi_shi_filenames.js          # 重命名 + 写映射
 *   node scripts/shorten_zhi_shi_filenames.js --verify # 仅校验映射与文件
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_DIR = process.env.DATA_DIR || path.resolve(__dirname, '../data');
const ZHI_SHI_DIR = path.join(DATA_DIR, 'zhi_shi_html');
const MAP_PATH = path.join(ZHI_SHI_DIR, 'filename_map.json');
const ID_RE = /^((?:cwwl|cwwn|life|tlen|cont|llen|seer)_[^_]+)/;

const SUBDIR_BY_PREFIX = {
  cwwl: 'read_cwwl_v2',
  cwwn: 'read_cwwn_v2',
  life: 'read_life_v2',
};

function parseZhiShiXinXi(jsText) {
  const start = jsText.indexOf('{');
  let depth = 0;
  for (let i = start; i < jsText.length; i += 1) {
    if (jsText[i] === '{') depth += 1;
    else if (jsText[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        return JSON.parse(jsText.slice(start, i + 1));
      }
    }
  }
  throw new Error('Failed to parse 1_zhi_shi_xin_xi.js');
}

function getSubdir(id) {
  const prefix = id.split('_')[0];
  return SUBDIR_BY_PREFIX[prefix] || 'read_others_v2';
}

function fileHash(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function buildPlan(index) {
  const groups = new Map();

  for (const [key, value] of Object.entries(index)) {
    const match = key.match(ID_RE);
    if (!match) {
      throw new Error(`无法解析 ID: ${key}`);
    }
    const id = match[1];
    const subdir = getSubdir(id);
    const longName = `${id}_${value}.json`;
    const groupKey = `${subdir}\0${id}`;
    if (!groups.has(groupKey)) groups.set(groupKey, []);
    groups.get(groupKey).push({ key, value, id, subdir, longName });
  }

  const byKey = {};
  const byLongName = {};
  const renames = [];

  for (const [, items] of groups) {
    items.sort((a, b) => a.key.localeCompare(b.key, 'zh-CN'));
    items.forEach((item, idx) => {
      const shortName = items.length === 1
        ? `${item.id}.json`
        : (idx === 0 ? `${item.id}.json` : `${item.id}__${idx + 1}.json`);
      const relPath = `${item.subdir}/${shortName}`.replace(/\\/g, '/');
      const longRel = `${item.subdir}/${item.longName}`.replace(/\\/g, '/');
      byKey[item.key] = relPath;
      byLongName[item.longName] = shortName;
      byLongName[longRel] = relPath;
      renames.push({
        key: item.key,
        subdir: item.subdir,
        longName: item.longName,
        shortName,
        relPath,
        longPath: path.join(ZHI_SHI_DIR, item.subdir, item.longName),
        shortPath: path.join(ZHI_SHI_DIR, item.subdir, shortName),
      });
    });
  }

  return { byKey, byLongName, renames };
}

function applyRenames(renames) {
  let renamed = 0;
  let skipped = 0;

  for (const row of renames) {
    const { longPath, shortPath, longName, shortName } = row;

    if (longName === shortName) {
      if (!fs.existsSync(shortPath)) {
        throw new Error(`缺失文件: ${shortPath}`);
      }
      skipped += 1;
      continue;
    }

    const longExists = fs.existsSync(longPath);
    const shortExists = fs.existsSync(shortPath);

    if (longExists && shortExists) {
      if (fileHash(longPath) !== fileHash(shortPath)) {
        throw new Error(`短名与长名内容不一致: ${shortPath}`);
      }
      fs.unlinkSync(longPath);
      skipped += 1;
      continue;
    }

    if (!longExists && shortExists) {
      skipped += 1;
      continue;
    }

    if (!longExists && !shortExists) {
      throw new Error(`长名与短名文件均不存在: ${longPath}`);
    }

    fs.renameSync(longPath, shortPath);
    renamed += 1;
  }

  return { renamed, skipped };
}

function verifyPlan(index, map) {
  let ok = 0;
  const errors = [];

  for (const [key, value] of Object.entries(index)) {
    const rel = map.byKey[key];
    if (!rel) {
      errors.push(`map 缺少 key: ${key}`);
      continue;
    }
    const filePath = path.join(ZHI_SHI_DIR, rel);
    if (!fs.existsSync(filePath)) {
      errors.push(`文件不存在: ${rel} (key=${key})`);
      continue;
    }
    const content = fs.readFileSync(filePath, 'utf8');
    if (!content.trim()) {
      errors.push(`文件为空: ${rel}`);
      continue;
    }
    ok += 1;
  }

  for (const row of buildPlan(index).renames) {
    const bytes = Buffer.byteLength(row.shortName, 'utf8');
    if (bytes > 255) {
      errors.push(`短名仍超 255 字节 (${bytes}): ${row.shortName}`);
    }
  }

  return { ok, errors, total: Object.keys(index).length };
}

function main() {
  const verifyOnly = process.argv.includes('--verify');

  const indexPath = path.join(DATA_DIR, 'private', '1_zhi_shi_xin_xi.js');
  const index = parseZhiShiXinXi(fs.readFileSync(indexPath, 'utf8'));
  const plan = buildPlan(index);

  console.log(`索引条目: ${Object.keys(index).length}`);
  console.log(`计划短名文件: ${plan.renames.length}`);

  if (!verifyOnly) {
    const { renamed, skipped } = applyRenames(plan.renames);
    const mapDoc = {
      version: 1,
      generatedAt: new Date().toISOString(),
      byKey: plan.byKey,
      byLongName: plan.byLongName,
    };
    fs.writeFileSync(MAP_PATH, JSON.stringify(mapDoc), 'utf8');
    console.log(`重命名: ${renamed}，跳过: ${skipped}`);
    console.log(`已写入: ${MAP_PATH}`);
  } else if (!fs.existsSync(MAP_PATH)) {
    console.error('filename_map.json 不存在，请先运行不带 --verify 的脚本');
    process.exit(1);
  }

  const map = verifyOnly
    ? JSON.parse(fs.readFileSync(MAP_PATH, 'utf8'))
    : { byKey: plan.byKey, byLongName: plan.byLongName };

  const result = verifyPlan(index, map);
  console.log(`校验通过: ${result.ok}/${result.total}`);

  if (result.errors.length) {
    console.error('错误:');
    result.errors.slice(0, 20).forEach((e) => console.error(' -', e));
    if (result.errors.length > 20) {
      console.error(` ... 另有 ${result.errors.length - 20} 条`);
    }
    process.exit(1);
  }

  console.log('✅ zhi_shi_html 短文件名方案校验通过');
}

main();
