# Server Account Console

一个面向内网单管理员场景的 Linux 物理机账户、公钥与配置同步控制台。

初版能力：维护主机与 Linux 用户，手动选择目标机器，预检后执行账户、公钥、权限、软链接和受控后置脚本，并保留逐机执行记录。

## 设计

完整的初版需求与技术方案见 [设计文档](docs/superpowers/specs/2026-07-14-server-account-console-design.md)。实施分解见 [实施计划](docs/superpowers/plans/2026-07-14-server-account-console.md)。

## 开发环境

后端要求 Python 3.13，前端要求 Node.js 22。复制 `.env.example` 到 `.env` 后，设置管理员密码哈希、随机会话密钥和控制 SSH 私钥路径。运行 `docker compose up --build` 后，从 `http://localhost:8080` 访问控制台。

## 计划技术栈

- React + shadcn/ui
- FastAPI + Ansible Runner
- SQLite
- Docker Compose
