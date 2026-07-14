from pathlib import Path


def test_host_operations_role_only_uses_fixed_user_operations() -> None:
    role = Path(__file__).parents[2] / "ansible" / "roles" / "host_operations" / "tasks" / "main.yml"
    content = role.read_text(encoding="utf-8")

    assert "ansible.builtin.getent" in content
    assert "ansible.builtin.user" in content
    assert "ansible.builtin.lineinfile" in content
    assert "ansible.builtin.copy" in content
    assert "no_log: true" in content
    assert "ansible.builtin.shell" not in content


def test_sshd_role_validates_before_reloading_service() -> None:
    role = Path(__file__).parents[2] / "ansible" / "roles" / "host_operations" / "tasks" / "main.yml"
    content = role.read_text(encoding="utf-8")

    assert "PasswordAuthentication" in content
    assert "99-server-account-console.conf" in content
    assert "sshd -T" in content
    assert "sshd -t" in content
    assert content.index("sshd -t") < content.index("Reload SSH service")
