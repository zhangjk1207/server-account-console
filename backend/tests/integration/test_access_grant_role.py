from pathlib import Path


def test_access_grant_role_creates_only_a_controlled_home_link() -> None:
    root = Path(__file__).parents[2] / "ansible" / "roles" / "access_grant"
    provision = (root / "tasks" / "provision.yml").read_text(encoding="utf-8")

    assert "Create user data directory" in provision
    assert "create_home: false" in provision
    assert "Assert existing home is the controlled link" in provision
    assert "access_grant.data_directory" in provision
    assert "state: link" in provision
    assert "force: false" in provision
    assert "not ansible_check_mode" in provision
    assert "Replace authorized keys with the enabled member key set" in provision
    assert "access_grant_user.public_keys | join" in provision


def test_access_grant_role_only_removes_data_when_explicitly_requested() -> None:
    root = Path(__file__).parents[2] / "ansible" / "roles" / "access_grant"
    revoke = (root / "tasks" / "revoke.yml").read_text(encoding="utf-8")

    assert "Assert home link and account are managed before removal" in revoke
    assert "access_grant_home.stat.exists" in revoke
    assert "access_grant.delete_data | bool" in revoke
    assert "Remove controlled user data directory" in revoke
    assert "state: absent" in revoke
