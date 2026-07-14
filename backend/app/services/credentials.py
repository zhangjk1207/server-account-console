from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization

from app.core.config import get_settings


MAX_PRIVATE_KEY_BYTES = 64 * 1024


class CredentialConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialCipher:
    fernet: Fernet

    @classmethod
    def from_settings(cls) -> "CredentialCipher":
        key = get_settings().credential_encryption_key
        if not key:
            raise CredentialConfigurationError("未配置凭证加密主密钥")
        try:
            return cls(Fernet(key.encode()))
        except (TypeError, ValueError) as error:
            raise CredentialConfigurationError("凭证加密主密钥无效") from error

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self.fernet.decrypt(token.encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as error:
            raise CredentialConfigurationError("无法解密主机凭证") from error


def validate_private_key(data: bytes) -> str:
    if not data or len(data) > MAX_PRIVATE_KEY_BYTES:
        raise ValueError("私钥文件格式无效")
    if b"ENCRYPTED" in data or b"bcrypt" in data.lower():
        raise ValueError("不支持带口令的私钥")
    try:
        if b"BEGIN OPENSSH PRIVATE KEY" in data:
            serialization.load_ssh_private_key(data, password=None)
        elif b"BEGIN" in data and b"PRIVATE KEY" in data:
            serialization.load_pem_private_key(data, password=None)
        else:
            raise ValueError("私钥文件格式无效")
    except TypeError as error:
        raise ValueError("不支持带口令的私钥") from error
    except ValueError as error:
        raise ValueError("私钥文件格式无效") from error
    return data.decode("utf-8")
