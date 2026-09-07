"""使用操作系统凭据库保存用户自己的模型密钥。"""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError, NoKeyringError

SERVICE_NAME = "cn.filemate.campus-twin.deepseek"
ACCOUNT_NAME = "api-key"


class CredentialStoreError(RuntimeError):
    """操作系统安全凭据库不可用。"""


def _ensure_available() -> None:
    """确认当前系统存在可写的安全凭据后端。"""
    try:
        priority = float(keyring.get_keyring().priority)
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise CredentialStoreError("当前系统未提供可用的安全凭据库") from exc
    if priority <= 0:
        raise CredentialStoreError("当前系统未提供可用的安全凭据库")


def secure_store_available() -> bool:
    """返回操作系统安全凭据库是否可用。"""
    try:
        _ensure_available()
    except CredentialStoreError:
        return False
    return True


def get_stored_api_key() -> str:
    """读取当前系统用户保存的 DeepSeek API 密钥。"""
    try:
        _ensure_available()
        return (keyring.get_password(SERVICE_NAME, ACCOUNT_NAME) or "").strip()
    except (CredentialStoreError, KeyringError, NoKeyringError):
        return ""


def set_stored_api_key(api_key: str) -> None:
    """将 DeepSeek API 密钥写入当前系统用户的安全凭据库。"""
    try:
        _ensure_available()
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, api_key)
    except (CredentialStoreError, KeyringError, NoKeyringError) as exc:
        raise CredentialStoreError("无法写入系统安全凭据库") from exc


def delete_stored_api_key() -> bool:
    """删除当前系统用户保存的 DeepSeek API 密钥。"""
    if not get_stored_api_key():
        return False
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except (KeyringError, NoKeyringError) as exc:
        raise CredentialStoreError("无法从系统安全凭据库删除密钥") from exc
    return True


def resolve_api_key() -> tuple[str, str]:
    """按本机安全凭据、环境变量的顺序解析模型密钥。"""
    stored_key = get_stored_api_key()
    if stored_key:
        return stored_key, "secure_store"
    environment_key = os.environ.get("LLM_API_KEY", "").strip()
    if environment_key:
        return environment_key, "environment"
    return "", "none"
