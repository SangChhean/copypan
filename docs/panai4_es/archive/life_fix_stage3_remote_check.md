# 生命读经修订 阶段3 remote_check

> 2026-11-06T13:04:01；log=`G:\copypan\logs\life_fix_apply_20261106_125639.log`

- C1 version=8.19.0 cluster=docker-cluster count=55841 emb_ok=True
- C1 embedding_spec={'type': 'dense_vector', 'dims': 1024, 'similarity': 'cosine', 'index_options': {'type': 'int8_hnsw', 'm': 16, 'ef_construction': 100}}
- 连接变量名：ES_REMOTE_HOST, ES_REMOTE_PORT, ES_REMOTE_USERNAME, ES_REMOTE_PASSWORD
- C2 vs es_before：same=348 diff=0 missing=0
- C3 seed=20261106 field same/diff=300/0；vec100 same/diff=100/0
- C4 set_eq=True local=55841 remote=55841 aff_diff=348 non_aff_diff=0
- C5：**通过**（C2 全同且非受影响无差异）

