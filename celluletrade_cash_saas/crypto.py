"""Chiffrement symétrique (Fernet) des clés API Binance stockées en base."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from celluletrade_cash_saas import config


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = config.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY n'est pas configurée. Générez-en une avec :\n"
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_value(value):
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(token):
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
