# 阶段 7 · 服务器部署检查清单（摘录）

## 本机免登录开关

- **服务器环境文件里绝不能有 `QA4_DEV_AUTOLOGIN`；部署前用 grep 检查为 0。**

```bash
# 在服务器 env / 单元文件 / 部署目录中检查；命中行数应为 0
grep -R "QA4_DEV_AUTOLOGIN" /opt/qa4_data /etc/systemd/system --include='*.env' --include='*.service' 2>/dev/null | wc -l
```

该变量仅供本机 `restart_qa4.bat` 调试；线上即使误开，非回环绑定也会拒绝启动，但仍应以配置层杜绝。

## 数据与静态资源

- **圣经数据**：把本机 `qa4/data/bible_data/` **整个目录**传到服务器；`QA4_DATA_DIR` 指向含该目录的数据根（与配置读取路径一致）。
- **诗歌**：代码侧仍可能回退读 Windows 本机诗歌目录；**服务器上 `qa4_hymns`（或等价）ES 索引必须完整导入**，否则按首数/歌词取诗会失败。
- **生命读经 PDF**：`/lsm/`（或前端静态映射的 LSM PDF）放到服务器静态目录，保证经文/生命读经相关页能打开 PDF。

## 外部依赖与密钥（不在仓库填值）

上线环境需自行配置（勿提交 `.env`）：

- **Gemini**（英文翻译等）：`GEMINI_API_KEY` / `QA4_GEMINI_API_KEY`
- **MiniMax 朗读**：`MINIMAX_API_KEY` + `MINIMAX_GROUP_ID`（或 `QA4_*` 同名）
- **OpenAI**（语音 ASR）：`OPENAI_API_KEY` / `QA4_OPENAI_API_KEY`
- **OpenCC**（简繁）：Python 包 `opencc-python-reimplemented`（见 `qa4/backend/requirements.txt`）
- 部署前核对 `requirements.txt` 是否有本批新增依赖并已安装

（`QA4_DEV_AUTOLOGIN` 上线前 grep 为 0：见上文，不重复。）
