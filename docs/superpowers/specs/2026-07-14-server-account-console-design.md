# 物理机账户与公钥管理控制台：初版需求与技术方案

**状态：** 已确认设计  
**日期：** 2026-07-14  
**使用者与评审者：** 单一管理员  
**部署范围：** 内网；约十几台 Linux 物理机

## 1. 问题陈述

当前在多台 Linux 物理机上为人员创建系统账户、配置 SSH 公钥、设置目录权限和软链接，需要逐台手工登录完成。该过程缺少可选择的目标范围、变更预览、统一执行结果和历史记录，重复操作容易遗漏或造成配置不一致。

## 2. 目标与非目标

### 目标

- 在一个中文 Web 界面中维护机器、Linux 用户、用户的多个 SSH 公钥和脚本模板。
- 每次针对一个用户，由管理员手动勾选目标机器；执行前运行预检并展示逐机计划变更；确认后才修改机器。
- 通过幂等自动化完成账户、组、公钥、sudo、目录权限、软链接和已选后置脚本。
- 保存任务的输入快照、模板版本、逐机日志和结果，可安全重跑失败任务。
- 展示机器的 SSH 可用性和最近探测时间。

### 非目标

- 不提供多用户协作、RBAC、SSO、审批流或堡垒机终端。
- 不管理密码轮换、云资产同步、Windows/macOS、LDAP/AD 或容器/Kubernetes 身份。
- 不在 MVP 中实现完整资源监控、告警、任意在线 Shell 或自动定时同步。

## 3. 约束与假设

- 控制台仅由一个管理员在内网使用。
- 运行控制台的主机可使用一把管理员 SSH 私钥连接所有受管 Linux 主机，并可使用 `sudo`。
- 初始规模不超过 20 台主机和 20 个受管用户；每次最多操作 20 台主机。
- 机器可使用不同的 SSH 登录用户名，但共享同一控制端私钥。

## 4. 总体方案

使用 React + shadcn/ui 构建前端；FastAPI 作为 API 与任务控制端；Ansible Runner 负责远程配置；SQLite 保存业务数据和任务记录。所有服务使用 Docker Compose 在内网部署。

```text
React + shadcn/ui
        │ REST / SSE
FastAPI
 ├─ SQLite
 ├─ Ansible Runner
 └─ 只读挂载的 SSH 私钥
        │ SSH + sudo
Linux 物理机
```

选择 Ansible 而非后端直接执行 SSH 命令：用户、公钥、文件权限和软链接均可声明为期望状态；重复执行不会重复修改，且能获得结构化的逐机结果。

### 4.1 任务状态机

```text
draft -> preview_running -> ready_to_confirm -> running -> succeeded
                                              └-> partial_failed
preview_running -> preview_failed
ready_to_confirm -> expired
```

- `preview_running` 使用 Ansible `--check` 预检，不应修改目标主机。
- 预检成功后，任务冻结用户、公钥、机器、脚本模板和变量的快照，进入 `ready_to_confirm`。
- 仅能从预检任务创建正式执行。预检 30 分钟后过期，避免按过期配置执行。
- 单台主机失败不会中断其他主机；整体结果为 `partial_failed`。
- 不自动回滚。管理员修复原因后重跑同一快照或重新发起任务。

### 4.2 并发与超时

- 全局同一时间仅运行一个正式任务；预检也不得与正式任务并行。
- Ansible 默认并发为 5 台主机。
- 单台主机超时 5 分钟，单个任务总超时 20 分钟。
- 页面刷新后可通过任务详情恢复状态和日志；SSE 断开后从已保存日志继续拉取。

## 5. 功能需求与界面

### 5.1 概览

- 展示主机总数、SSH 可用/不可用数量、最近一次任务和最近失败项。
- 仅提供跳转，不在此页发起危险操作。

### 5.2 机器

- 表格字段：名称、地址、端口、SSH 用户、标签、SSH 状态、最后探测、最后同步。
- 可创建、编辑、归档机器；删除前必须确认没有未完成任务引用该机器。
- 创建和变更地址后，必须进行 SSH 测试并由管理员确认主机指纹后方可用于任务。
- 标签用于筛选与批量勾选，不自动决定同步范围。

### 5.3 用户和 SSH 公钥

- 受管用户字段：Linux 用户名、显示名、主组、附加组、Shell、家目录、sudo 配置、启用状态。
- 一个用户可关联多个 SSH 公钥；存储公钥内容、OpenSSH 指纹、注释、启用状态。
- 用户详情展示每台机器的最近同步状态，并提供“同步到机器”入口。

### 5.4 同步向导

1. 从用户详情选择目标机器。机器以可勾选列表呈现，显示标签、连通状态和上次同步结果。
2. 选择“创建或更新”动作及零或一个后置脚本模板。
3. 发起预检，展示每台机器的连通性、计划动作和预检错误。
4. 管理员确认后执行正式任务，实时查看逐机日志和最后结果。

### 5.5 脚本模板和记录

- 脚本模板字段：名称、说明、正文、版本号、启用状态。
- 仅能选择保存且启用的模板；MVP 不支持临时输入任意脚本。
- 每次任务复制并保存模板正文与版本；历史记录永远显示实际执行版本。
- 执行记录提供按状态、用户、机器、时间筛选以及“使用同一输入重跑”。

## 6. 数据模型

| 实体 | 关键字段 | 说明 |
|---|---|---|
| `hosts` | name, address, port, ssh_user, tags, host_key_fingerprint, status | 受管 Linux 主机 |
| `managed_users` | username, display_name, primary_group, groups, shell, home, sudo_rule, enabled | 目标系统账户定义 |
| `ssh_public_keys` | managed_user_id, public_key, fingerprint, comment, enabled | 一个用户的多个公钥 |
| `script_templates` | name, description, body, version, enabled | 可审计的后置脚本 |
| `jobs` | kind, state, user_snapshot, request_snapshot, script_snapshot, timestamps | 预检或正式任务 |
| `job_targets` | job_id, host_id, state, output, error, timing | 单台主机执行结果 |
| `host_user_state` | host_id, managed_user_id, last_success_job_id, synced_at, desired_hash | 用户在主机上的最近成功状态 |

所有 ID 使用 UUID。任务快照使用 JSON，保留请求时的用户、公钥、主机、脚本和参数；正常查询字段仍保持关系化，避免把业务状态只放入 JSON。

## 7. API 设计

| 方法与路径 | 用途 |
|---|---|
| `GET/POST /api/hosts` | 查询和创建机器 |
| `PATCH/DELETE /api/hosts/{id}` | 修改、归档机器 |
| `POST /api/hosts/{id}/test` | 测试 SSH 并请求确认指纹 |
| `GET/POST /api/users` | 查询和创建受管用户 |
| `GET/PATCH/DELETE /api/users/{id}` | 查看、修改、禁用用户 |
| `POST/DELETE /api/users/{id}/keys` | 管理用户 SSH 公钥 |
| `GET/POST/PATCH /api/script-templates` | 管理后置脚本模板 |
| `POST /api/jobs/preview` | 创建预检任务；输入用户、机器和可选模板 |
| `POST /api/jobs/{id}/execute` | 确认并执行通过预检的任务 |
| `GET /api/jobs` 与 `GET /api/jobs/{id}` | 查询任务及逐机结果 |
| `GET /api/jobs/{id}/events` | SSE 推送任务和日志事件 |
| `POST /api/jobs/{id}/rerun` | 以历史快照创建新的预检任务 |

所有写入接口返回 `409` 表示任务锁冲突，返回 `422` 表示业务校验失败，返回 `503` 表示 Ansible 执行环境不可用。

## 8. Ansible 契约

后端对每个任务创建独立临时目录，包含静态 inventory、任务快照变量和允许使用的脚本文件。Playbook 只接受后端生成的结构化变量，禁止把用户输入直接插入命令字符串。

固定执行顺序：

```text
SSH 主机密钥校验 -> become
-> 用户组、用户和家目录
-> .ssh 目录与 authorized_keys
-> sudoers
-> 目录权限和软链接
-> 后置脚本
-> 收集最终状态
```

- `authorized_keys` 默认增加本系统管理的公钥，不移除目标机上其他公钥。
- 删除公钥或删除用户是独立的未来动作，不包含在“创建或更新”。
- 后置脚本通过只读输入 JSON 获取任务变量；不得以字符串拼接生成 Shell 命令。
- 后置脚本失败标记该主机失败，但保留此前已经成功的幂等配置结果。

## 9. 安全设计

- 控制台仅通过内网访问，仍使用本地管理员密码登录；密码以 bcrypt 哈希保存。
- 会话 Cookie 使用 `HttpOnly`、`SameSite=Lax`；跨站写请求使用 CSRF Token。
- 优先由内网反向代理提供 TLS；若确实为纯 HTTP，部署文档必须限制监听地址和防火墙来源。
- SSH 私钥不写入 SQLite、不出现在 API、日志或任务快照中；通过 Docker secret 或只读文件挂载提供。
- 已确认主机指纹后启用严格校验。发现指纹变化时阻止任务并要求人工重新确认。
- SQLite、日志和备份目录对容器运行用户设置最小权限；数据库每日备份并保留 14 天。

## 10. 监控与可观测性

- MVP 每 5 分钟进行 TCP 22 和 SSH 登录探测，记录机器状态与延迟。
- FastAPI 输出健康检查和基础运行指标；Docker 日志记录 API 和任务控制端错误。
- 完整 CPU、内存、磁盘、硬件和告警放入第二阶段，通过 Node Exporter + Prometheus 接入；不影响初版交付。

## 11. 测试和验收

### 测试

- 单元测试：用户名与公钥校验、主机指纹状态转换、任务状态机、模板快照和权限校验。
- 集成测试：用临时 SSH 容器验证用户、公钥、目录权限和软链接；重复执行两次，第二次不得产生变更。
- API 测试：预检、确认、锁冲突、主机不可达、脚本失败和重跑。
- 前端端到端测试：机器勾选、预检结果、确认执行、SSE 日志和历史任务查看。

### MVP 验收

1. 可对一个用户手动勾选 1 至 20 台机器，完成预检、确认、执行和日志查看。
2. 同一任务重复执行不重复创建用户或公钥，目录权限和软链接正确。
3. 一台机器不可达或脚本失败时，其他机器继续执行，失败步骤在任务详情可定位。
4. 修改脚本模板后，历史任务仍可显示原始脚本版本与输入快照。
5. 私钥不会出现在数据库、API 响应或任何执行日志中。

## 12. 交付顺序

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| 基础 | Docker Compose、数据库迁移、管理员登录、机器 CRUD 与 SSH 测试 | 能添加并确认主机 |
| 身份 | 用户、公钥、脚本模板 CRUD | 能维护期望状态 |
| 自动化 | Playbook、预检、确认执行、SSE 和任务记录 | 能安全同步到多台主机 |
| 收尾 | 健康探测、备份、端到端测试、部署文档 | 满足所有 MVP 验收项 |

## 13. 后续方向

- Node Exporter + Prometheus 的资源监控和告警。
- 多管理员、RBAC 和操作审批。
- 用户禁用/删除、公钥撤销、任务并发和计划任务。
- Git 同步脚本模板及配置审查。
