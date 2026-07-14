import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.services.credentials import CredentialCipher, CredentialConfigurationError, validate_private_key


def test_credential_cipher_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        cipher = CredentialCipher.from_settings()
        assert cipher.decrypt(cipher.encrypt("sudo-secret")) == "sudo-secret"
    finally:
        get_settings.cache_clear()


def test_credential_cipher_requires_a_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(CredentialConfigurationError, match="未配置凭证加密主密钥"):
            CredentialCipher.from_settings()
    finally:
        get_settings.cache_clear()


def test_private_key_validation_rejects_invalid_or_encrypted_key() -> None:
    with pytest.raises(ValueError, match="私钥文件格式无效"):
        validate_private_key(b"not a private key")

    with pytest.raises(ValueError, match="不支持带口令的私钥"):
        validate_private_key(b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nexample\n-----END ENCRYPTED PRIVATE KEY-----\n")
