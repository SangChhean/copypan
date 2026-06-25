// front_anshifenliang — 搜索 API 配置
// 生产环境由 nginx 将 /api 反代到 back_anshifenliang:8020
// 本地 npx serve 时自动指向 :8020
window.API_BASE = window.API_BASE || (
  (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
    ? 'http://localhost:8020'
    : ''
);