# 部署

## 本地试运行

1. 在仓库根目录复制 `.env.example` 为 `.env`。生成并持久保存 Fernet 主密钥；它用于加密 SQLite 中的每台机器私钥和 sudo 密码，丢失后无法解密已有凭证：

   ```sh
   .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

2. 将输出设置为 `CREDENTIAL_ENCRYPTION_KEY`，再生成管理员密码哈希：

   ```sh
   .venv/bin/python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
   ```

3. 将输出设置为 `ADMIN_PASSWORD_HASH`，并为 `SESSION_SECRET` 设置至少 32 字节的随机值。
4. 启动 API：`cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/uvicorn app.main:app --reload --port 8000`。
5. 新开终端启动前端：`cd frontend && npm run dev -- --port 5174`，然后访问 `http://127.0.0.1:5174`。开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 内网部署

1. 按上述方式准备 `.env` 和 `runtime/`，并将 `CREDENTIAL_ENCRYPTION_KEY` 存入部署环境或密钥管理系统；不要将实际值提交到 Git。
2. 仅允许内网或 VPN 网段访问反向代理；生产环境通过反向代理启用 TLS。
3. 执行 `docker compose up -d --build`。API 容器在启动时自动执行数据库迁移。
4. 首次访问时，在机器页面逐台打开详情，上传无口令的 OpenSSH/PEM 私钥文件和 sudo 密码，然后测试 SSH/sudo。首次测试会要求带外确认 ED25519 指纹；未确认、指纹变化或 sudo 未通过的机器不能成为同步目标。
5. API 默认每 24 小时创建一次 SQLite 在线备份，保留 14 天；可通过 `BACKUP_INTERVAL_SECONDS` 调整周期。也可执行 `DATABASE_PATH=./runtime/app.db scripts/backup.sh` 立即创建备份。恢复时停止服务并以备份文件替换 `runtime/app.db`。

私钥文件、sudo 密码、`CREDENTIAL_ENCRYPTION_KEY`、`.env`、运行数据、Ansible 产物和备份均不得提交。当前不支持带口令的私钥；应使用只供控制台使用、权限受限的专用密钥。修改 SSH 密码登录会先预检并要求确认，写入后验证 `sshd`；验证或 reload 失败时自动恢复原有片段。
