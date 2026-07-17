from pathlib import Path


ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "access_grant" / "tasks"


def test_access_grant_role_routes_created_and_adopted_accounts_to_separate_tasks() -> None:
    main = (ROLE / "main.yml").read_text(encoding="utf-8")

    assert "provision_adopted.yml" in main
    assert "revoke_adopted.yml" in main
    assert "account_origin | default('created') == 'adopted'" in main


def test_adopted_provision_only_validates_unlocks_and_appends_keys() -> None:
    tasks = (ROLE / "provision_adopted.yml").read_text(encoding="utf-8")

    assert "ansible.builtin.getent" in tasks
    assert "access_grant.remote_uid" in tasks
    assert "access_grant.remote_home" in tasks
    assert "password_lock: false" in tasks
    assert "ansible.builtin.lineinfile" in tasks
    assert "state: present" in tasks
    assert "state: absent" not in tasks
    assert "groups:" not in tasks
    assert "sudo" not in tasks


def test_adopted_revoke_only_removes_managed_keys_and_locks_account() -> None:
    tasks = (ROLE / "revoke_adopted.yml").read_text(encoding="utf-8")

    assert "ansible.builtin.getent" in tasks
    assert "access_grant.managed_public_keys" in tasks
    assert "ansible.builtin.lineinfile" in tasks
    assert "state: absent" in tasks
    assert "password_lock: true" in tasks
    assert "state: present" in tasks
    assert "remove: true" not in tasks
    assert "ansible.builtin.file" not in tasks
