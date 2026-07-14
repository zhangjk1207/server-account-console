from pathlib import Path


def test_role_transfers_post_script_and_json_input_to_the_target() -> None:
    tasks = (Path(__file__).parents[2] / "ansible" / "roles" / "managed_user" / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "post_script_content" in tasks
    assert "task_input_json" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "post_script_path" not in tasks
