# 阶段 7 · 服务器部署检查清单（摘录）

## 本机免登录开关

- **服务器环境文件里绝不能有 `QA4_DEV_AUTOLOGIN`；部署前用 grep 检查为 0。**

```bash
# 在服务器 env / 单元文件 / 部署目录中检查；命中行数应为 0
grep -R "QA4_DEV_AUTOLOGIN" /opt/qa4_data /etc/systemd/system --include='*.env' --include='*.service' 2>/dev/null | wc -l
```

该变量仅供本机 `restart_qa4.bat` 调试；线上即使误开，非回环绑定也会拒绝启动，但仍应以配置层杜绝。
