const { setupEnvironment } = require('../lib/bootstrap');

(async () => {
  const e = await setupEnvironment();
  for (const q of ['新约', '旧约', '圣经', '目录', '新约的职事']) {
    const r = await e.search(q, '经节');
    const msg = r.message || '';
    const titles = [...msg.matchAll(/<span class="data-title[^"]*">([^<]+)<\/span>/g)].map((m) => m[1]);
    const catalogs = [...msg.matchAll(/data-book-key="([^"]+)"/g)].map((m) => m[1]);
    console.log(`\n=== ${q} ===`);
    console.log('found:', r.found);
    console.log('titles:', titles);
    console.log('catalog keys:', catalogs);
  }
})();
