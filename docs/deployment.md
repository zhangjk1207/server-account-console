# 部署

## 本地试运行

1. 创建控制私钥并设置权限为 `0600`；目标机器上的 `root` 或指定 SSH 用户必须能够使用该密钥登录，并具备免密 `sudo`。
2. 在仓库根目录复制 `.env.example` 为 `.env`，将 `CONTROL_SSH_KEY_PATH` 设为该私钥的绝对路径，并生成管理员密码哈希：

   ```sh
   .venv/bin/python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
   ```

3. 将输出设置为 `ADMIN_PASSWORD_HASH`，并为 `SESSION_SECRET` 设置至少 32 字节的随机值。
4. 启动 API：`cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/uvicorn app.main:app --reload --port 8000`。
5. 新开终端启动前端：`cd frontend && npm run dev`，然后访问 Vite 输出的本地地址。开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 内网部署

1. 按上述方式准备 `.env`、`runtime/` 和 `0600` 的控制私钥。
2. 仅允许内网或 VPN 网段访问反向代理；生产环境通过反向代理启用 TLS。
3. 执行 `docker compose up -d --build`。API 容器在启动时自动执行数据库迁移。
4. 首次访问时，在机器页面逐台测试 SSH 并确认主机指纹；未确认或指纹变化的机器不能成为同步目标。
5. 每日执行 `scripts/backup.sh`，备份保留 14 天。恢复时停止服务并以备份文件替换 `runtime/app.db`。

控制私钥、`.env`、运行数据、Ansible 产物和备份均被 Git 忽略，不得提交。
