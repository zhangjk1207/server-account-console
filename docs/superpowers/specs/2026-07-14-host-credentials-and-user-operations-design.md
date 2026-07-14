# 主机凭证与用户运维设计

**状态：** 已确认，待规格复核
**日期：** 2026-07-14
**范围：** 内网单管理员的 Server Account Console 扩展

## 1. 目标

为每台 Linux 主机保存加密的 SSH 和 sudo 凭证，在保存后验证 SSH 登录与 sudo；在控制台中读取和维护该主机已有的本地用户；安全切换 SSH 密码登录；修复右侧工作区垂直居中的布局。

本设计扩展既有“用户/公钥同步”功能，不引入任意远程终端、多管理员或密码轮换策略。

## 2. 凭证与安全边界

每台主机最多一份可替换的连接凭证，包含：

- SSH 私钥；
- sudo 密码。

新增环境变量 `CREDENTIAL_ENCRYPTION_KEY`，值为 Fernet URL-safe base64 密钥。后端使用该密钥加密凭证的每个字段后保存到 SQLite。密钥只存在部署环境或 Docker secret，不写入 `.env.example` 的实际值、SQLite、日志、API 响应、任务快照和备份。

私钥通过 multipart 文件上传提交，服务端只接受不超过 64 KiB 的 OpenSSH/PEM 私钥文本，不保留原始文件名。API 仅返回凭证是否已配置、最近验证时间、SSH/sudo 验证状态和脱敏错误摘要。替换或清除凭证需要 CSRF 校验。运行时将私钥写到任务私有目录中的 `0600` 临时文件，任务结束后删除。

保存凭证不要求已有可用连接。首次“测试凭证”先扫描 ED25519 主机密钥；未确认的主机只返回待确认指纹。管理员确认后立即以该主机凭证进行严格登录和 sudo 验证。已确认主机的验证按以下顺序执行：

1. 使用已确认的 ED25519 主机指纹建立严格 known_hosts；
2. 使用配置的 SSH 用户和私钥运行 `true`；
3. 通过 stdin 向 `sudo -S -k -p '' true` 传入 sudo 密码，强制绕过 sudo 缓存。

任何凭证内容都不得出现在 Ansible 事件、错误详情、审计消息或浏览器状态中。既有全局控制私钥仅作为旧部署兼容项；新建连接、用户运维和用户同步一律优先使用每台主机自己的凭证。

## 3. 数据模型与 API

新增 `host_credentials`，与 `hosts` 一对一：

| 字段 | 说明 |
|---|---|
| `host_id` | 主机外键，唯一 |
| `private_key_ciphertext` | 加密私钥 |
| `sudo_password_ciphertext` | 加密 sudo 密码 |
| `verified_at` | 最近成功或失败测试时间 |
| `ssh_verified` / `sudo_verified` | 最近验证结果 |
| `last_error` | 不包含秘密的错误摘要 |

新增接口：

- `GET/PUT/DELETE /api/hosts/{id}/credentials`：读取状态、上传加密保存或清除凭证；
- `POST /api/hosts/{id}/credentials/test`：扫描或立即测试 SSH 与 sudo；
- `GET /api/hosts/{id}/users`：读取该主机的非系统本地用户；
- `POST /api/hosts/{id}/user-operations/preview`：预检用户或 SSHD 操作；
- `POST /api/host-operations/{job_id}/execute`：确认后执行；
- `GET /api/hosts/{id}/ssh-password-authentication`：读取有效密码登录状态；
- `POST /api/hosts/{id}/ssh-password-authentication/preview`：预检开启或关闭。

主机凭证或用户运维任务沿用任务、逐机目标和 SSE 事件模型。读取用户是只读任务，可直接执行；变更用户或 SSHD 必须先预检、人工确认并使用全局任务锁。

## 4. 固定远程操作

远程操作全部使用 Ansible Runner 和固定 playbook/role，不提供任意命令输入。

### 4.1 用户读取

使用 `getent passwd` 和 `getent group` 获取本地用户与组，默认展示 UID 不低于 `1000` 的用户；可选择展示 `root`，但 root 只读。返回 UID、用户名、主组、附加组、Shell、家目录、锁定状态和账户到期信息。不会读取或返回 `/etc/shadow` 密码哈希。

### 4.2 用户变更

允许的动作是：创建/编辑、锁定/解锁、重置密码、删除、设置组、Shell、家目录、SSH 公钥、sudo 规则和账户到期时间。删除支持“保留家目录”或“同时删除家目录”两个明确选项。

操作表单可以选择控制台的受管人员，以复用其用户名、Shell、组、目录定义和启用的 SSH 公钥，也允许对未关联的已有本地用户进行受控维护。用户详情读取该用户现有的 `authorized_keys` 指纹和注释，支持添加、移除指定公钥或以已选公钥集合替换；移除或替换都必须明确确认。公钥本身可显示和审计，私钥永不涉及此功能。

用户新密码仅作为一次性敏感输入传入任务，使用 `no_log` 任务设置，不持久化。删除、重置密码和删除家目录在执行前要求前端单独确认。

### 4.3 SSH 密码登录

密码登录状态来自 `sshd -T` 的有效配置。切换操作写入控制台专属的 `/etc/ssh/sshd_config.d/99-server-account-console.conf`，同时管理 `PasswordAuthentication` 与 `KbdInteractiveAuthentication`，避免 PAM 键盘交互仍保留密码通道：

1. 预检目标状态和 sudo 能力；
2. 写入临时配置，执行 `sshd -t`；
3. 原子替换专属片段，再 reload `sshd` 或 `ssh` 服务；
4. 验证最终有效状态。

失败时不替换现有片段。已有 SSH 会话不被主动关闭；关闭密码登录前，界面显示需要保留可用密钥登录通道。

## 5. 前端

机器详情新增四个顶对齐区域：

1. 连接凭证：私钥文件上传、sudo 密码及保存/清除；
2. 连接验证：主机指纹、SSH 与 sudo 最近结果，提供重新测试；
3. 现有用户：列表、筛选和固定操作表单；
4. SSH 登录策略：读取状态、开启/关闭、预检与确认。

所有秘密输入使用 `type=password` 或受控多行输入，保存成功后立即清空。任务详情继续显示状态和日志，但不会显示秘密。

布局调整为工作区从顶部对齐：侧栏与主内容容器使用 `align-items: start`，主工作区不使用会导致垂直居中的 `margin: auto` 或 `place-items: center`。登录页继续保持居中。

## 6. 错误处理与审计

- 未配置凭证时，凭证测试、用户读取和运维操作返回可操作的 422 错误；
- 指纹未确认或变化时，所有需要连接的操作被阻断；
- SSH 登录成功但 sudo 失败时，显示两个独立状态，禁止需要 sudo 的操作；
- SSHD 校验或 reload 失败时，任务目标失败，保留原专属配置；
- 任一敏感操作失败时，任务事件仅记录操作类型和脱敏错误。
- Ansible Runner 的 inventory、extra vars、原始事件与进程环境只写入执行期间的临时目录；结束后整体删除，任务记录仅保留脱敏事件。

## 7. 测试与验收

- 加密服务：相同主密钥可解密、错误主密钥被拒绝、序列化与日志不含明文；
- API：凭证写入不回显、SSH/sudo 结果分别持久化、未验证主机或未配置凭证被拒绝；
- 任务服务：每个用户操作与 SSHD 开关只能走固定 playbook，敏感变量不进入事件；
- Ansible：用户读取不返回 shadow 数据；用户锁定、解锁、重置、删除、SSHD 片段校验和 reload 路径具有静态与容器集成覆盖；
- 前端：保存凭证后清空字段，确认门控危险操作，布局在桌面与移动端顶部对齐；
- 浏览器流程：配置凭证、测试 SSH/sudo、查询用户、预检并确认密码登录开关。

验收标准：管理员可以持久保存每台主机的凭证、独立判断 SSH 与 sudo 是否生效，安全查看和维护已有用户，并在预检确认后打开或关闭 SSH 密码登录；任何秘密均不能通过数据库明文、API、日志或任务快照获取。
