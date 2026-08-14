# Server Account Console

面向内网**单管理员**场景的 Agent-native Linux 访问控制面。管理员用自然语言描述目标，pi Agent 读取受控证据并形成计划；FastAPI 与 Ansible 负责预检、人工批准和确定性执行。

> ⚠️ 这是一个带有实际系统权限的控制面项目。仓库内**不包含任何真实密钥、API Key 或主机凭证**；所有私密配置都必须通过环境变量注入。

## 核心能力

- **Agent 工作台**：以对话方式描述运维目标，Agent 读取机器的经授权证据并为每个变更形成结构化计划；左栏管理运维会话，右栏展示任务概览、工具轨迹与详情。
- **成员与开通**：维护团队成员及其 SSH 公钥，按机器批量创建或纳管账号并授予受控权限。
- **机器管理**：每台机器独立保存加密的 SSH 私钥与 sudo 密码，支持验证 SSH/sudo、确认主机指纹、盘点已有用户、安全切换 SSH 密码登录。
- **权限模板**：可复用声明补充组与 sudo 规则的模板，落在 Access Grant 上。
- **受控执行**：读取型检查可自动执行；任何服务、软件包、账户或文件变更必须生成计划并等待管理员批准（预检 → 确认 → 执行），全程保留逐机运行记录。

## 架构

```text
管理员
  │
  ▼
Agent Workbench (React) ── prompt + SSE 事件
  │
  ▼
pi Agent Runtime (TypeScript) ---- 白名单领域工具
  │
  ▼
Control Plane (FastAPI) ──── SQLite
  │        (不可变预检 / 批准门禁)
  ▼
Ansible Runner ──── 受管机器
```

### 信任边界

1. Agent 只能通过鉴权 API 元数据与状态。
2. Agent 只能通过类型化领域工具构造**预检**，无法拼装任意 shell 命令。
3. 预检是不可变的 Plan 候选；状态漂移时会使其失效。
4. 只有管理员能批准执行，且批准范围限定到对应的预检标识与快照。
5. FastAPI 在真正执行前这些校验完生成凭证、指纹、授权状态与快照。
6. 密钥任何都不会进入 prompt、消息、工具结果、计划快照或事件流。

初始工具集刻意保持在很小：

`get_control_plane_overview`、`list_machines`、`list_members`、`get_member_access`、`list_recent_runs`

## 目录结构

```text
backend/           FastAPI + Ansible Runner 控制面（SQLite）
frontend/          React Agent Workbench（对话工作台、机器页、模型设置）
agent-runtime/     pi coding agent 运行时（TypeScript，8010）
docs/              架构、设计与运维文档
compose.yml        内网 Docker Compose 编排
.env.example       环境变量模板（不要提交真实值）
```

## 开发环境

后端要求 **Python 3.13**，前端要求 **Node.js 22**。

### 1. 复制环境变量模板并填入真实值

```powershell
Copy-Item .env.example .env
# 编辑 .env：
#   ADMIN_PASSWORD_HASH       管理员密码的 bcrypt 哈希
#   SESSION_SECRET            随机会话签名密钥
#   CREDENTIAL_ENCRYPTION_KEY Fernet 主密钥（务必长期妥善保管，丢失则无法解密主机凭证）
#   AGENT_RUNTIME_TOKEN       Agent Runtime 调用控制面的内部令牌
```

### 2. 分别启动三个进程（Windows PowerShell）

```powershell
# 后端（端口 8003）
cd backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8003

# Agent Runtime（端口 8010）
cd ..\agent-runtime
$env:CONTROL_PLANE_URL = "http://127.0.0.1:8003"
npm run dev

# 前端（Vite dev server）
cd ..\frontend
npm run dev
```

- `AGENT_RUNTIME_TOKEN` 必须与后端 `.env` 中的取值一致，否则 Agent Runtime 将返回 `Agent Runtime 未授权`。
- 前端默认把 `/api` 代理到 `8003`、`/agent` 代理到 `8010`；如需改目标，设置 `VITE_API_TARGET`／`VITE_AGENT_TARGET`。
- 未接入任何机器与模型前，工作台会停留在机载引导的"完成引导才能提问"。

### 运行测试

```powershell
cd backend      # ..\.venv\Scripts\pytest.exe
cd frontend     npm test
cd agent-runtime npm test
```

## 部署

内网部署可使用容器（`docker compose up --build`），将后端、Agent Runtime、前端打包为 3 个服务，并以环境变量注入全部机密：

```powershell
Copy-Item .env.example .env   # 填好真实值后
docker compose up --build
# 访问 http://localhost:8080
```

## 安全说明

私钥文件、sudo 密码、`CREDENTIAL_ENCRYPTION_KEY`、`.env`、运行数据与备份均不得提交，已通过 `.gitignore` 排除。Ansible 运行产物只在执行期间临时存在，结束后自动删除；当前不支持带口令的私钥，建议使用仅控制台使用的专用受限密钥。

## 文档

- [服务器访问控制面设计](docs/superpowers/specs/2026-07-14-server-account-console-design.md)
- [主机凭证与用户运维扩展设计](docs/superpowers/specs/2026-07-14-host-credentials-and-user-operations-design.md)
- [Agent 架构与信任边界](docs/agent-architecture.md)
- [逐主机加密凭证决策 ADR-001](docs/decisions/001-per-host-encrypted-credentials.md)
- [部署与运维文档](docs/deployment.md)