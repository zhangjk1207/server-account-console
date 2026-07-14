# Server Account Console

一个面向内网单管理员场景的 Linux 物理机账户、公钥与配置同步控制台。

初版能力：维护主机与 Linux 用户，手动选择目标机器，预检后执行账户、公钥、权限、软链接和受控后置脚本，并保留逐机执行记录。

## 设计

完整的初版需求与技术方案见 [设计文档](docs/superpowers/specs/2026-07-14-server-account-console-design.md)。

## 计划技术栈

- React + shadcn/ui
- FastAPI + Ansible Runner
- SQLite
- Docker Compose
