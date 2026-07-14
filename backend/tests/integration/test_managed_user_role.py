from pathlib import Path


def test_sync_role_removes_managed_sudo_policy_when_rule_is_empty() -> None:
    role = Path(__file__).parents[2] / "ansible" / "roles" / "managed_user" / "tasks" / "main.yml"
    content = role.read_text(encoding="utf-8")

    assert "Remove managed sudo policy when no rule is declared" in content
    assert 'path: "/etc/sudoers.d/server-account-{{ desired_user.username }}"' in content
    assert "state: absent" in content
    assert "desired_user.sudo_rule | default('', true) | length == 0" in content
