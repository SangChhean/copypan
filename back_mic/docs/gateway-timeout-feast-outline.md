# 节期纲目 / AI 接口网关超时说明

听抄稿纲目生成会连续调用 1～3 次 Claude（主纲目 + 序言 + 添言），总耗时可能超过 2 分钟。若网关（如 Nginx）默认超时 60s 或 120s，会先返回 **504 Gateway Time-out**，而后端仍在继续生成。

**复合的纲目**在听抄稿纲目与晨兴纲目都成功之后，会再请求一次 Claude，同样可能较慢；若前一步因超时失败，复合也会失败，需先解决听抄稿/晨兴接口的超时与稳定性。

工具箱前端会对 `generate/transcript`、`generate/composite` 等接口使用较长等待；**瓶颈通常在反向代理的 `proxy_read_timeout`**，而不是浏览器。

## 1. 后端已做的优化

- **序言 / 添言并行**：听抄稿生成时，序言纲目与添言纲目已改为并行请求 Claude，总耗时由「主 + 序 + 添」变为「主 + max(序, 添)」，可缩短几十秒。

## 2. 网关需调大超时（必做）

在 **Nginx** 中为 AI 相关接口单独加大超时，例如：

```nginx
# 在 server 或 location 中，对 /api/ai_search 路径加大超时（单位：秒）
location /api/ai_search/ {
    proxy_pass http://backend;
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    proxy_read_timeout 300;   # 建议 300（5 分钟）或更大，听抄稿+序言+添言可能需 2～4 分钟
}
```

若使用 **其他反向代理**（如 Caddy、云厂商负载均衡），请把「读超时 / 后端超时」调到 **300 秒（5 分钟）** 或以上。

## 3. 如何确认

- 调大超时后，听抄稿生成应能正常返回 200，不再出现 504。
- 若仍偶发 504，可再适当增大 `proxy_read_timeout`（例如 600）。
