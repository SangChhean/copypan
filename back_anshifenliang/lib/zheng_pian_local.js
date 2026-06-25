const fs = require('fs');
const path = require('path');

const ID_RE = /^((?:cwwl|cwwn|life|tlen|cont|llen|seer)_[^_]+)/;

const SUBDIR_BY_PREFIX = {
  cwwl: 'read_cwwl_v2',
  cwwn: 'read_cwwn_v2',
  life: 'read_life_v2',
};

let filenameMapCache = null;

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

function loadFilenameMap(dataDir) {
  if (filenameMapCache) return filenameMapCache;

  const mapPath = path.join(dataDir, 'zhi_shi_html', 'filename_map.json');
  if (!fs.existsSync(mapPath)) {
    filenameMapCache = { byKey: {}, byLongName: {} };
    return filenameMapCache;
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(mapPath, 'utf8'));
    filenameMapCache = {
      byKey: parsed.byKey || {},
      byLongName: parsed.byLongName || {},
    };
  } catch (err) {
    console.warn('[zheng_pian] filename_map.json 解析失败，回退长文件名:', err.message);
    filenameMapCache = { byKey: {}, byLongName: {} };
  }

  return filenameMapCache;
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

function resolveZhengPianPath(dataDir, key, trimmed, id, subdir) {
  const map = loadFilenameMap(dataDir);
  const zhiShiRoot = path.join(dataDir, 'zhi_shi_html');

  const mappedRel = map.byKey[key];
  if (mappedRel) {
    const mappedPath = path.join(zhiShiRoot, mappedRel);
    if (fs.existsSync(mappedPath)) return mappedPath;
  }

  const legacyName = `${id}_${trimmed}.json`;
  const mappedLegacy = map.byLongName[legacyName];
  if (mappedLegacy) {
    const legacyMappedPath = path.join(zhiShiRoot, subdir, mappedLegacy);
    if (fs.existsSync(legacyMappedPath)) return legacyMappedPath;
  }

  const legacyPath = path.join(zhiShiRoot, subdir, legacyName);
  if (fs.existsSync(legacyPath)) return legacyPath;

  return null;
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
  const filePath = resolveZhengPianPath(dataDir, key, trimmed, id, subdir);

  if (!filePath) return null;
  return fs.readFileSync(filePath, 'utf8');
}

module.exports = {
  loadValueToKeyMap,
  readLocalZhengPian,
  loadFilenameMap,
  resolveZhengPianPath,
};
