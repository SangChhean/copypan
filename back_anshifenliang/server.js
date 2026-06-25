/**
 * 按时分粮搜索 API
 * POST /api/search  { query, category?, lang? }
 * GET  /api/health
 */
const express = require('express');
const cors = require('cors');
const path = require('path');
const { setupEnvironment, DATA_DIR } = require('./lib/bootstrap');
const { loadValueToKeyMap, readLocalZhengPian } = require('./lib/zheng_pian_local');
const { getDetailFromEnv } = require('./lib/detail');
const { isReady: isFooJieReady } = require('./lib/foo_jie_single');

const PORT = parseInt(process.env.PORT || '8020', 10);
const ZHENG_PIAN_API = process.env.ZHENG_PIAN_API
  || 'https://uz7bcgrc1i.execute-api.us-east-1.amazonaws.com/test/Model-retrieval-claude-3-5-sonnet-test';
const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

let searchEnv = null;
let valueToKey = null;
let ready = false;

async function init() {
  console.log('Loading search data into memory...');
  const t0 = Date.now();
  valueToKey = loadValueToKeyMap(DATA_DIR);
  console.log(`[zheng-pian] value→key index: ${valueToKey.size} entries`);
  searchEnv = await setupEnvironment();
  ready = true;
  console.log(`[foo_jie_single] ${isFooJieReady() ? 'index ready' : 'index missing — run node scripts/build_foo_jie_index.js'}`);
  console.log(`Ready in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

app.get('/api/health', (_req, res) => {
  res.json({ status: ready ? 'ok' : 'loading', data_dir: DATA_DIR });
});

app.post('/api/search', async (req, res) => {
  if (!ready) {
    return res.status(503).json({ error: 'Server still loading data' });
  }

  const { query, category, lang } = req.body || {};
  if (!query || typeof query !== 'string' || !query.trim()) {
    return res.status(400).json({ error: 'query is required' });
  }

  try {
    const result = await searchEnv.search(
      query.trim(),
      category || null,
      lang || 'zh-CN',
    );
    res.json(result);
  } catch (err) {
    console.error('Search error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/detail', async (req, res) => {
  if (!ready) {
    return res.status(503).json({ error: 'Server still loading data' });
  }

  const { source, title, lang } = req.body || {};
  if (!source || typeof source !== 'string') {
    return res.status(400).json({ error: 'source is required' });
  }
  if (!title || typeof title !== 'string' || !title.trim()) {
    return res.status(400).json({ error: 'title is required' });
  }

  try {
    const detail = getDetailFromEnv(searchEnv, source.trim(), title.trim(), lang || 'zh-CN');
    if (!detail) {
      return res.status(404).json({ error: 'not found' });
    }
    res.json(detail);
  } catch (err) {
    console.error('Detail error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/is-traditional', (req, res) => {
  if (!ready) {
    return res.status(503).json({ error: 'Server still loading data' });
  }
  const { text } = req.body || {};
  const w = searchEnv.window;
  const traditional = typeof w.isTraditionalText === 'function'
    ? w.isTraditionalText(String(text || ''))
    : false;
  res.json({ traditional, lang: traditional ? 'zh-TW' : 'zh-CN' });
});

// 参考信息 [1][2] 按钮 — 本地 zhi_shi_html/ 优先，找不到再代理 AWS
app.post('/api/zheng-pian', async (req, res) => {
  const { message } = req.body || {};
  if (!message || typeof message !== 'string' || !message.trim()) {
    return res.status(400).json({ error: 'message is required' });
  }

  const trimmed = message.trim();

  try {
    const localHtml = readLocalZhengPian(trimmed, DATA_DIR, valueToKey);
    if (localHtml) {
      return res.json({ data: { response: localHtml } });
    }

    const upstream = await fetch(ZHENG_PIAN_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: trimmed }),
    });
    const text = await upstream.text();
    res.status(upstream.status).type('application/json').send(text);
  } catch (err) {
    console.error('zheng-pian error:', err);
    res.status(502).json({ error: err.message });
  }
});

// 静态资源：private/ 全文 HTML（供前端查看全文）
app.use('/private', express.static(path.join(DATA_DIR, 'private')));

init().then(() => {
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`back_anshifenliang listening on :${PORT}`);
  });
}).catch((err) => {
  console.error('Failed to start:', err);
  process.exit(1);
});
