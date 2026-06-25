/**
 * 从 /api/search 返回的 HTML message 解析结构化条目（与网站列表一致）
 */
function parseSearchItems(htmlMessage, maxResults = 20) {
  if (!htmlMessage || typeof htmlMessage !== 'string') return [];

  const items = [];

  // 带「查看全文」按钮的条目（问答、注解、诗歌、经节问答等）
  const blockRe = /<p[^>]*>\s*<span class="(?:data-title(?:_\d+)?|hymn-title)"[^>]*>([^<]+)<\/span>\s*<button class="view-original"([^>]*)>[\s\S]*?<\/button>\s*<\/p>([\s\S]*?)(?=<p[^>]*>\s*<span class="(?:data-title(?:_\d+)?|hymn-title)"|<p style|$)/gi;

  let m;
  while ((m = blockRe.exec(htmlMessage)) !== null && items.length < maxResults) {
    const title = m[1].trim();
    const btnAttrs = m[2];
    const previewHtml = (m[3] || '').trim();

    const sourceM = btnAttrs.match(/data-source="([^"]+)"/);
    if (!sourceM) continue;

    const titleKeyM = btnAttrs.match(/data-(?:title|title_3|book-key)="([^"]+)"/);
    const titleKey = titleKeyM ? titleKeyM[1].trim() : title;

    items.push({
      title,
      source: sourceM[1].trim(),
      titleKey,
      previewHtml,
    });
  }

  if (items.length >= maxResults) return items;

  // 诗歌：纯数字编号返回多首候选（诗歌第1首　查看全文<br>...）
  for (const seg of htmlMessage.split(/<br\s*\/?>/gi)) {
    if (items.length >= maxResults) break;
    const hymnPick = seg.trim().match(/^(.+?)　查看全文\s*$/);
    if (!hymnPick) continue;
    const displayTitle = hymnPick[1].trim();
    if (!displayTitle || displayTitle.includes('<')) continue;
    if (items.some((it) => it.titleKey === displayTitle && it.source === 'hymns')) continue;
    items.push({
      title: displayTitle,
      source: 'hymns',
      titleKey: displayTitle,
      previewHtml: '',
    });
  }

  if (items.length >= maxResults) return items;

  // 诗歌 / 注解：单首或单条直出 <strong>标题</strong>\n正文
  if (!items.length) {
    const directM = htmlMessage.match(/^<strong>([\s\S]*?)<\/strong>\s*([\s\S]*)$/);
    if (directM) {
      const title = directM[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
      const preview = (directM[2] || '').trim();
      if (title) {
        let source = null;
        if (title.includes('节注')) {
          source = 'zhu_jie_html';
        } else if (/注\d/.test(title) && /恢复本圣经|^.+注\d+/.test(title)) {
          source = 'foo_jie_single';
        } else if (/第.+章$/.test(title)) {
          source = 'jing_wen_with_index';
        } else if (/诗歌第|补充本诗歌第|儿童诗歌第/.test(title)) {
          source = 'hymns';
        }
        if (source) {
          items.push({
            title,
            source,
            titleKey: title,
            previewHtml: preview,
          });
        }
      }
    }
  }

  if (items.length >= maxResults) return items;

  // 圣经经文直查（无按钮，绿色标题 + 正文）
  const verseRe = /<div[^>]*border-left:\s*4px\s+solid\s+#4CAF50[^>]*>[\s\S]*?<p[^>]*>([^<]+)<\/p>[\s\S]*?<p[^>]*>([\s\S]*?)<\/p>[\s\S]*?<\/div>|<p[^>]*font-weight:\s*bold[^>]*>([^<]+)<\/p>\s*<p[^>]*line-height:\s*1\.5[^>]*>([\s\S]*?)<\/p>/gi;

  while ((m = verseRe.exec(htmlMessage)) !== null && items.length < maxResults) {
    const title = (m[1] || m[3] || '').trim();
    const content = (m[2] || m[4] || '').trim();
    if (!title) continue;

    // 避免与已解析条目重复
    if (items.some((it) => it.title === title && it.source === 'bible_verse')) continue;

    items.push({
      title,
      source: 'bible_verse',
      titleKey: title,
      previewHtml: content,
    });
  }

  return items;
}

module.exports = { parseSearchItems };
