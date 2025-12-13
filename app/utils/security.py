"""
Утилиты безопасности для авторизации админки

Пароли в БД не хранятся в открытом виде
В таблице admin_users хранится только password_hash
Для хэширования использую bcrypt
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """ Хэширует пароль для сохранения в БД.
    Используется при создании админа/менеджера. """
    return _pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """ Проверяет введённый пароль по хэшу из БД """
    return _pwd_context.verify(password, password_hash)
