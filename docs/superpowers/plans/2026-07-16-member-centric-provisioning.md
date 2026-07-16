# 成员中心批量开通执行计划

> **给执行者：** 本计划按任务顺序执行。每项先写失败测试，再实现最小代码使其通过；不要在真实机器上进行写操作作为自动化验证。

**目标：** 将控制台的日常操作改为成员中心的批量 SSH 密钥账号开通和回收：管理员为机器配置数据根目录，在每个目标机器上为成员独立选择用户名与权限模板，并受控地建立数据目录及 `/home/{username}` 软链接。

**架构：** 保留 `ManagedUser`、每机连接凭据和通用 `Job` 审计模型。新增权限模板和成员-机器授权记录，并以一个固定 Ansible 角色完成 provision/revoke；预检快照固化每行用户名、模板覆盖与计算出的数据目录。前端默认进入成员与开通工作台，机器页面只承担连接和数据根目录等低频配置。

**技术栈：** FastAPI、SQLAlchemy/Alembic、Ansible Runner、React、TypeScript、Vite、shadcn-ui、Vitest、pytest。

---

## 任务 1：建立授权领域模型和机器数据根目录

**文件：**
- 修改：`backend/app/db/models.py`
- 新增：`backend/alembic/versions/004_member_access_grants.py`
- 修改：`backend/app/schemas/host.py`
- 新增：`backend/app/schemas/access_grant.py`
- 修改：`backend/app/schemas/__init__.py`
- 修改：`backend/tests/test_models.py`
- 新增：`backend/tests/api/test_permission_templates.py`
- 新增：`backend/tests/api/test_access_grants.py`

**步骤：**
1. 为主机加入可空 `data_root`，这样已有机器不会因迁移失效；新授权必须拒绝未配置或非绝对数据根目录的机器。
2. 新增全局 `PermissionTemplate`（名称、描述、附加组、可选 sudo 规则、启用状态）和每成员每机器唯一的 `HostAccessGrant`（用户名、模板快照、覆盖值、计算数据目录、状态、最近成功任务）。
3. 添加 Pydantic 输入/输出模型，用户名、组和路径复用已有的规范化/校验规则；不得让客户端提交最终数据目录。
4. 写迁移，保留历史表和记录；为新表建立成员、机器、状态和唯一授权约束。

## 任务 2：提供模板、授权预检和执行 API

**文件：**
- 新增：`backend/app/api/permission_templates.py`
- 新增：`backend/app/api/access_grants.py`
- 修改：`backend/app/main.py`
- 修改：`backend/app/api/users.py`
- 修改：`backend/app/services/jobs.py`
- 新增：`backend/app/services/access_grants.py`
- 修改：`backend/tests/api/test_permission_templates.py`
- 修改：`backend/tests/api/test_access_grants.py`
- 修改：`backend/tests/services/test_jobs.py`

**步骤：**
1. 先写 API 测试覆盖模板 CRUD、每行独立用户名、模板覆盖、无启用公钥/不可连接主机/无数据根目录的拒绝路径。
2. 实现模板 CRUD 和成员授权列表。成员的旧 `host-states` 仅作兼容，不作为新界面来源。
3. 实现授权批次创建：请求只接收 host、用户名、模板和明确的覆盖值；服务端从主机数据根目录计算目录，并将完整不可变快照写入 `Job` 与 `JobTarget`。
4. 预检、确认执行和任务状态复用现有单 Runner 锁、连接凭据复核、30 分钟确认过期与审计事件。执行成功后仅更新对应的授权记录；失败不把授权误标为有效。
5. 回收批次按授权记录创建；每行 `delete_data` 默认 false，且只能回收当前成员-机器匹配记录。

## 任务 3：实现固定、可回收的 Ansible 授权角色

**文件：**
- 新增：`backend/ansible/access_grant.yml`
- 新增：`backend/ansible/roles/access_grant/tasks/main.yml`
- 新增：`backend/ansible/roles/access_grant/tasks/provision.yml`
- 新增：`backend/ansible/roles/access_grant/tasks/revoke.yml`
- 修改：`backend/app/services/jobs.py`
- 新增：`backend/tests/integration/test_access_grant_role.py`
- 修改：`backend/tests/services/test_jobs.py`

**步骤：**
1. 先用本地 Ansible integration 测试定义 provision：创建用户但不创建普通 home、创建受控数据目录、建立 `/home/{username}` 指向计算目录的链接、写入公钥并应用组/sudo。
2. 实现严格断言：数据目录必须正好位于配置数据根目录之下；已有 home 只能是指向同一数据目录的软链接；禁止覆盖普通目录或未知链接。
3. 实现 revoke 测试和角色：删除账户和受控 home 链接；仅在明确 `delete_data` 时删除精确数据目录。路径/链接/账户不匹配时失败，绝不递归猜测删除。
4. 将新 `Job.kind` 的 runner 请求映射到新 playbook，继续使用私有临时目录、固定 inventory 和每机解密的管理凭据；密钥和 sudo 密码绝不进入数据库快照或日志。

## 任务 4：重建成员与开通工作台及机器配置界面

**文件：**
- 修改：`frontend/src/api.ts`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`frontend/src/App.test.tsx`
- 修改：`frontend/src/api.test.ts`

**步骤：**
1. 先加前端测试：选择成员后展示机器授权表；每行可勾选、修改用户名、选择模板；数据目录由机器配置计算展示；回收时删除数据目录默认关闭。
2. 用“成员与开通”作为默认页面。成员侧边栏和详情区只保留人员资料、公钥和授权概览；将低频的 Linux 目录、脚本字段移出主流程。
3. 实现紧凑批量表与清晰的预检/确认状态，在确认前展示不可变结果。高级组/sudo 覆盖收在展开行中，保持默认视图可扫描。
4. 在机器页面新增和编辑数据根目录，明确标示未配置状态并阻止该机被开通勾选。新增权限模板管理视图。
5. 重做色彩、排版、密度和状态组件，避免嵌套卡片和误导性的“等待中”；保留执行记录用于追踪失败与回滚处理。

## 任务 5：迁移、验证与交付

**文件：**
- 修改：`README.md`（若已有运行说明则补充，否则不创建营销文档）
- 修改：必要的运行配置或测试文件

**步骤：**
1. 执行 Alembic upgrade，在副本数据库验证旧数据可以升级。
2. 运行全部后端 pytest、Ansible syntax/integration 测试、前端 Vitest 与 production build。
3. 以 tmux 启动 API（仅 `127.0.0.1:8003`）和前端 preview（`0.0.0.0:5174`），检查 `/api/health` 经代理可用；不对真实机器执行写入。
4. 审阅 diff、确认测试输出后，直接提交并推送 `main`，使用 `jkzhang <zhangjikang@idata.ah.cn>` 身份。
