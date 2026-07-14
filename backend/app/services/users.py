import subprocess


def parse_public_key(public_key: str) -> tuple[str, str]:
    normalized = " ".join(public_key.strip().split())
    inspected = subprocess.run(
        ["ssh-keygen", "-lf", "-", "-E", "sha256"],
        input=f"{normalized}\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if inspected.returncode != 0:
        raise ValueError("SSH 公钥格式无效")
    fingerprint = next((part for part in inspected.stdout.split() if part.startswith("SHA256:")), None)
    if fingerprint is None:
        raise ValueError("无法计算 SSH 公钥指纹")
    key_parts = normalized.split(maxsplit=2)
    comment = key_parts[2] if len(key_parts) == 3 else ""
    return normalized, fingerprint, comment


def normalize_groups(groups: list[str]) -> list[str]:
    return sorted({group.strip() for group in groups if group.strip()})
