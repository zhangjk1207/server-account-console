# MVP 发布验收清单

## 发布前

- [ ] `backend/.venv/bin/pytest -q` 通过。
- [ ] `frontend/npm test -- --run` 与 `frontend/npm run build` 通过。
- [ ] `backend/.venv/bin/ansible-playbook --syntax-check -i 'localhost,' -c local ansible/playbook.yml` 通过。
- [ ] 在空 SQLite 数据库执行 `alembic upgrade head` 成功。
- [ ] `.env`、私钥文件、`CREDENTIAL_ENCRYPTION_KEY`、`runtime/`、备份和 Ansible 产物均未被 Git 跟踪。

## 人工验收

- [ ] 页面接入一台机器，带外核对并确认 SSH ED25519 指纹；指纹变化时同步被阻断。
- [ ] 创建一名用户和至少一把 SSH 公钥，在同步面板只勾选指定机器；未勾选机器不出现在任务目标中。
- [ ] 预检完成后，未勾选“我已确认以上变更”时不能执行；确认后检查逐机结果与实时日志。
- [ ] 使用目录、软链接和后置脚本各执行一次同步；同一输入重复执行不会产生重复目录、链接或授权公钥。
- [ ] 停用公钥、用户、脚本模板以及归档机器后，确认它们不能被新的同步任务选中。
- [ ] 在机器详情上传私钥文件和 sudo 密码，确认 SSH/sudo 独立通过；盘点已有用户、查看其公钥并预检一次锁定或公钥变更。
- [ ] 预检并确认一次 SSH 密码登录的开关；确认失败路径会恢复原有 SSH 配置。

## 上线后

- [ ] `GET /api/health` 返回数据库、Ansible 和凭证加密检查状态正常。
- [ ] 验证 `runtime/backups/` 出现可打开的 SQLite 备份，并记录恢复演练结果。
- [ ] 仅在内网或 VPN 后访问；反向代理已启用 TLS，凭证加密主密钥已备份到受控位置。
