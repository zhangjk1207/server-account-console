from app.services.command_previews import build_grant_command_preview


def test_adopted_provision_preview_appends_keys_without_changing_account_or_home() -> None:
    preview = build_grant_command_preview(
        "provision",
        {
            "account_origin": "adopted",
            "username": "legacy-alice",
            "remote_uid": 1007,
            "remote_primary_group": "research",
            "remote_home": "/srv/team homes/alice's",
        },
        ["ssh-ed25519 AAAA alice's key"],
    )

    commands = "\n".join(preview["commands"])
    assert "getent passwd legacy-alice" in commands
    assert "'/srv/team homes/alice'\"'\"'s/.ssh'" in commands
    assert "'ssh-ed25519 AAAA alice'\"'\"'s key'" in commands
    assert "usermod -U legacy-alice" in commands
    assert "useradd" not in commands
    assert "userdel" not in commands
    assert "ln -s" not in commands
    assert "rm -rf" not in commands
    assert preview["warnings"] == ["原有公钥不会被删除或覆盖"]


def test_adopted_revoke_preview_removes_only_recorded_keys_then_locks_account() -> None:
    preview = build_grant_command_preview(
        "revoke",
        {
            "account_origin": "adopted",
            "username": "legacy-alice",
            "remote_home": "/home/legacy-alice",
            "managed_public_keys": ["ssh-ed25519 AAAA platform-key"],
        },
        [],
    )

    commands = "\n".join(preview["commands"])
    assert "ssh-ed25519 AAAA platform-key" in commands
    assert "usermod -L legacy-alice" in commands
    assert "userdel" not in commands
    assert "rm -rf" not in commands
    assert "锁定后该账号的其他密钥也无法登录" in preview["warnings"]


def test_created_provision_preview_shows_controlled_data_path_and_home_link() -> None:
    preview = build_grant_command_preview(
        "provision",
        {
            "account_origin": "created",
            "username": "alice",
            "data_directory": "/mnt/train/alice",
            "groups": ["docker"],
            "sudo_rule": None,
        },
        ["ssh-ed25519 AAAA platform-key"],
    )

    commands = "\n".join(preview["commands"])
    assert "useradd" in commands
    assert "/mnt/train/alice" in commands
    assert "ln -s /mnt/train/alice /home/alice" in commands
    assert "ssh-ed25519 AAAA platform-key" in commands


def test_created_preview_includes_sudo_policy_and_valid_data_removal_commands() -> None:
    provision = build_grant_command_preview(
        "provision",
        {
            "account_origin": "created",
            "username": "alice",
            "data_directory": "/mnt/train/alice",
            "groups": [],
            "sudo_rule": "ALL=(ALL) NOPASSWD: /usr/bin/nvidia-smi",
        },
        ["ssh-ed25519 AAAA platform-key"],
    )
    revoke = build_grant_command_preview(
        "revoke",
        {
            "account_origin": "created",
            "username": "alice",
            "data_directory": "/mnt/train/alice",
            "delete_data": True,
        },
        [],
    )

    provision_commands = "\n".join(provision["commands"])
    revoke_commands = "\n".join(revoke["commands"])
    assert "/etc/sudoers.d/server-account-alice" in provision_commands
    assert "visudo -cf /etc/sudoers.d/server-account-alice" in provision_commands
    assert "rm -rf -- /mnt/train/alice" in revoke_commands
    assert "--one-file-system" not in revoke_commands
