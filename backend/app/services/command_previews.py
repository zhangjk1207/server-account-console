import shlex


def _quote(value: object) -> str:
    return shlex.quote(str(value))


def _append_key_command(authorized_keys: str, public_key: str) -> str:
    path = _quote(authorized_keys)
    key = _quote(public_key)
    return f"grep -qxF -- {key} {path} || printf '%s\\n' {key} >> {path}"


def _remove_key_command(authorized_keys: str, public_key: str) -> str:
    path = _quote(authorized_keys)
    key = _quote(public_key)
    return f"tmp=$(mktemp) && (grep -vxF -- {key} {path} > \"$tmp\" || true) && cat \"$tmp\" > {path} && rm -f \"$tmp\""


def _adopted_preview(operation: str, grant: dict, public_keys: list[str]) -> dict:
    username = str(grant["username"])
    home = str(grant["remote_home"])
    ssh_directory = f"{home.rstrip('/')}/.ssh"
    authorized_keys = f"{ssh_directory}/authorized_keys"
    identity = f"getent passwd {_quote(username)}"
    if operation == "provision":
        commands = [
            identity,
            f"usermod -U {_quote(username)}",
            f"install -d -m 700 -o {_quote(username)} -g {_quote(grant['remote_primary_group'])} {_quote(ssh_directory)}",
            f"touch {_quote(authorized_keys)}",
            f"chown {_quote(username)}:{_quote(grant['remote_primary_group'])} {_quote(authorized_keys)}",
            f"chmod 600 {_quote(authorized_keys)}",
            *[_append_key_command(authorized_keys, key) for key in public_keys],
        ]
        return {
            "label": "等价命令，实际由 Ansible 模块执行",
            "tasks": ["核对已有账号身份", "解锁账号", "保留并追加 SSH 公钥"],
            "commands": commands,
            "warnings": ["原有公钥不会被删除或覆盖"],
        }
    commands = [
        identity,
        *[_remove_key_command(authorized_keys, key) for key in grant.get("managed_public_keys", [])],
        f"usermod -L {_quote(username)}",
    ]
    return {
        "label": "等价命令，实际由 Ansible 模块执行",
        "tasks": ["核对已有账号身份", "移除平台追加的 SSH 公钥", "锁定账号"],
        "commands": commands,
        "warnings": ["锁定后该账号的其他密钥也无法登录", "账号、home 和数据不会被删除"],
    }


def _created_preview(operation: str, grant: dict, public_keys: list[str]) -> dict:
    username = str(grant["username"])
    data_directory = str(grant["data_directory"])
    home = f"/home/{username}"
    if operation == "provision":
        groups = [str(group) for group in grant.get("groups", [])]
        commands = [
            f"getent group {_quote(username)} || groupadd {_quote(username)}",
            *[f"getent group {_quote(group)} || groupadd {_quote(group)}" for group in groups],
            f"id -u {_quote(username)} >/dev/null 2>&1 || useradd -M -d {_quote(home)} -s /bin/bash -g {_quote(username)} {_quote(username)}",
        ]
        if groups:
            commands.append(f"usermod -aG {_quote(','.join(groups))} {_quote(username)}")
        commands.extend([
            f"install -d -m 750 -o {_quote(username)} -g {_quote(username)} {_quote(data_directory)}",
            f"ln -s {_quote(data_directory)} {_quote(home)}",
            f"install -d -m 700 -o {_quote(username)} -g {_quote(username)} {_quote(data_directory + '/.ssh')}",
            f"printf '%s\\n' {' '.join(_quote(key) for key in public_keys)} > {_quote(data_directory + '/.ssh/authorized_keys')}",
            f"chown {_quote(username)}:{_quote(username)} {_quote(data_directory + '/.ssh/authorized_keys')}",
            f"chmod 600 {_quote(data_directory + '/.ssh/authorized_keys')}",
        ])
        return {
            "label": "等价命令，实际由 Ansible 模块执行",
            "tasks": ["创建账号和数据目录", "创建 home 软链接", "安装成员 SSH 公钥", "应用权限模板"],
            "commands": commands,
            "warnings": [],
        }
    commands = [
        f"test \"$(readlink {_quote(home)})\" = {_quote(data_directory)}",
        f"rm {_quote(home)}",
        f"userdel {_quote(username)}",
        f"rm -f {_quote('/etc/sudoers.d/server-account-' + username)}",
    ]
    if grant.get("delete_data"):
        commands.append(f"rm -rf --one-file-system {_quote(data_directory)}")
    return {
        "label": "等价命令，实际由 Ansible 模块执行",
        "tasks": ["核对受控 home 软链接", "删除平台创建的账号", "按选择保留或删除数据目录"],
        "commands": commands,
        "warnings": [] if grant.get("delete_data") else ["数据目录将保留"],
    }


def build_grant_command_preview(operation: str, grant: dict, public_keys: list[str]) -> dict:
    """Return shell-quoted equivalents for review; these strings are never executed."""
    if operation not in {"provision", "revoke"}:
        raise ValueError("unsupported access grant operation")
    if grant.get("account_origin", "created") == "adopted":
        return _adopted_preview(operation, grant, public_keys)
    return _created_preview(operation, grant, public_keys)
