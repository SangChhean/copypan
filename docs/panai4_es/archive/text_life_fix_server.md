# text_life 服务器写入与对账（T4）

> 写入 2026-11-06T15:55–15:56（log `text_life_fix` 同轮）；S2 终检 16:02（`t4_s2`，knn `num_candidates=200`）。

- S0：count=39463；affected vs `es_server_before` same=5054 diff=0；本机↔服务器 _id 集合=39463；非受影响字段 same=34409 diff=0
- S1：bulk 覆盖写 **5054**；refresh 后 count=**39463**
- S2：本机↔服务器字段 **same=39463 diff=0**；向量（受影响+500）mism=**0**；knn **10/10**；smoke 列王纪=507 / 林前=1248 / 林后=987 / 腓立比=1072；旧写法与「，」=0；header 0/300
- 其他 panai4_* count 前后不变：bible=3691、outline_12490=55841、outline_feasts=11110、text_cwwl=178107、text_cwwn=32032、text_others=15481、map_note=16052、pano_catalog=53151、text_life=39463
- 回滚脚本 `panai4/inherit/rollback_text_life_remote.py`（未运行）
- 说明：首次 S2 knn 在 `num_candidates=50` 时 life_11-2-5 漏检（向量逐位相同）；改为 200 后 10/10。未回滚、未重写。
- **闸门 S0–S2：通过**

## 密钥泄露检查：通过
