const fs = require('fs');
const path = require('path');

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

function loadValueToKeyMap(dataDir) {
  const jsPath = path.join(dataDir, 'private', '1_zhi_shi_xin_xi.js');
  const obj = parseZhiShiXinXi(fs.readFileSync(jsPath, 'utf8'));
  const valueToKey = new Map();
  for (const [key, value] of Object.entries(obj)) {
    valueToKey.set(value, key);
  }
  return valueToKey;
}

function readLocalZhengPian(message, dataDir, valueToKey) {
  const trimmed = message.trim();
  const key = valueToKey.get(trimmed);
  if (!key) return null;

  const match = key.match(ID_RE);
  if (!match) return null;

  const id = match[1];
  const prefix = id.split('_')[0];
  const subdir = SUBDIR_BY_PREFIX[prefix] || 'read_others_v2';
  const filename = `${id}_${trimmed}.json`;
  const filePath = path.join(dataDir, 'zhi_shi_html', subdir, filename);

  if (!fs.existsSync(filePath)) return null;
  return fs.readFileSync(filePath, 'utf8');
}

module.exports = { loadValueToKeyMap, readLocalZhengPian };
