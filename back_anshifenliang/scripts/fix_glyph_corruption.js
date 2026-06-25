/**
 * 修复恢复本纲目 HTML 中 U+FFFD + 字母 的字体转码乱码
 * 用法: node scripts/fix_glyph_corruption.js
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.DATA_DIR || path.resolve(__dirname, '../data');
const MAP = { k: '祂', q: '痲', F: '镕', Z: '繸', m: '醡' };

function fixText(text) {
  if (!text.includes('\uFFFD')) return { text, changed: false };
  let changed = false;
  const fixed = text.replace(/\uFFFD(.)/g, (match, ch) => {
    if (MAP[ch]) {
      changed = true;
      return MAP[ch];
    }
    return match;
  });
  return { text: fixed, changed };
}

function walk(dir, exts) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const fp = path.join(dir, name);
    const st = fs.statSync(fp);
    if (st.isDirectory()) {
      out.push(...walk(fp, exts));
    } else if (exts.some((e) => name.endsWith(e))) {
      out.push(fp);
    }
  }
  return out;
}

function main() {
  const targets = [
    path.join(DATA_DIR, 'private/jing_wen_html'),
    path.join(DATA_DIR, 'zhi_shi_html'),
  ];

  let filesFixed = 0;
  let totalRepl = 0;

  for (const dir of targets) {
    if (!fs.existsSync(dir)) continue;
    const files = walk(dir, ['.html', '.json']);
    for (const fp of files) {
      const raw = fs.readFileSync(fp, 'utf8');
      if (!raw.includes('\uFFFD')) continue;
      const before = (raw.match(/\uFFFD./g) || []).length;
      const { text, changed } = fixText(raw);
      if (!changed) continue;
      fs.writeFileSync(fp, text, 'utf8');
      const after = (text.match(/\uFFFD./g) || []).length;
      filesFixed += 1;
      totalRepl += before - after;
      console.log(`fixed: ${path.relative(DATA_DIR, fp)} (${before - after} glyphs)`);
    }
  }

  console.log(`完成: ${filesFixed} 个文件, ${totalRepl} 处替换`);
}

main();
