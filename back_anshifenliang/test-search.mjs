const r = await fetch('http://localhost:8020/api/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: '经纶', category: '问答' }),
});
const d = await r.json();
const titles = [...(d.message || '').matchAll(/data-title">([^<]+)/g)].map(m => m[1]).slice(0, 5);
console.log(JSON.stringify({ found: d.found, query: d.query, titleCount: titles.length, titles }, null, 2));
