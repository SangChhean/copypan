/**
 * 从 bible_footnotes_html_加标签 构建单个注解索引（部署前运行一次）
 *
 * 用法:
 *   node scripts/build_foo_jie_index.js
 *   FOO_JIE_SOURCE="D:\path\to\bible_footnotes_html_加标签" node scripts/build_foo_jie_index.js
 */
const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.DATA_DIR || path.resolve(__dirname, '../data');
const SOURCE_DIR = process.env.FOO_JIE_SOURCE
  || 'D:\\001 工作项目\\属灵问答pansearch资料\\属灵问答--资料--处理工具\\【属灵问答】2--注解--资料--处理工具\\单个注解\\bible_footnotes_html_加标签';

const OUT_DIR = path.join(DATA_DIR, 'private/foo_jie_single');
const FILES_DIR = path.join(OUT_DIR, 'files');

function stripHtml(text) {
  return String(text || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractH3Title(html) {
  const m = String(html).match(/<h3[^>]*>([\s\S]*?)<\/h3>/i);
  return m ? stripHtml(m[1]) : '';
}

function shortTitleFromFilename(name) {
  const m = name.match(/恢复本圣经[，,](.+)\.json$/i);
  return m ? m[1].trim() : '';
}

function main() {
  const titlePath = path.join(OUT_DIR, 'title_index.json');
  if (!fs.existsSync(SOURCE_DIR)) {
    if (fs.existsSync(titlePath)) {
      console.log(`源目录不存在，跳过构建（已有索引: ${titlePath}）`);
      return;
    }
    console.error(`源目录不存在: ${SOURCE_DIR}`);
    console.error('请设置环境变量 FOO_JIE_SOURCE，或先提交 data/private/foo_jie_single/');
    process.exit(1);
  }

  fs.mkdirSync(FILES_DIR, { recursive: true });

  const titleIndex = {};
  const contentIndex = [];
  const files = fs.readdirSync(SOURCE_DIR).filter((f) => f.endsWith('.json'));

  console.log(`源目录: ${SOURCE_DIR}`);
  console.log(`输出目录: ${OUT_DIR}`);
  console.log(`文件数: ${files.length}`);

  let copied = 0;
  for (const fileName of files) {
    const srcPath = path.join(SOURCE_DIR, fileName);
    const destPath = path.join(FILES_DIR, fileName);

    if (!fs.existsSync(destPath)) {
      fs.copyFileSync(srcPath, destPath);
    }
    copied += 1;

    const raw = fs.readFileSync(srcPath, 'utf8');
    let html;
    try {
      html = JSON.parse(raw);
    } catch {
      html = raw;
    }
    if (typeof html !== 'string') continue;

    const h3Title = extractH3Title(html);
    const shortTitle = shortTitleFromFilename(fileName);
    const plain = stripHtml(html.replace(/<h3[\s\S]*?<\/h3>/i, ''));

    const keys = new Set();
    if (h3Title) keys.add(h3Title);
    if (shortTitle) {
      keys.add(shortTitle);
      keys.add(h3Title.replace(/恢复本圣经[　\s]+/, '') || shortTitle);
      keys.add(`恢复本圣经　${shortTitle}`);
    }

    for (const key of keys) {
      if (key) titleIndex[key] = fileName;
    }

    if (shortTitle && plain) {
      contentIndex.push({ title: shortTitle, file: fileName, text: plain });
    }

    if (copied % 2000 === 0) {
      console.log(`  已处理 ${copied}/${files.length}…`);
    }
  }

  fs.writeFileSync(
    path.join(OUT_DIR, 'title_index.json'),
    JSON.stringify(titleIndex, null, 0),
    'utf8',
  );
  fs.writeFileSync(
    path.join(OUT_DIR, 'content_index.json'),
    JSON.stringify(contentIndex, null, 0),
    'utf8',
  );

  console.log(`完成: 复制/索引 ${copied} 个文件`);
  console.log(`title_index 键数: ${Object.keys(titleIndex).length}`);
  console.log(`content_index 条数: ${contentIndex.length}`);
}

main();
