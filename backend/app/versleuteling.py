from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import instellingen


class VersleuteldeTekst(TypeDecorator):
    """Tekstkolom die versleuteld in de database staat en alleen in de applicatie leesbaar is."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return Fernet(instellingen().versleutelsleutel).encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Fernet(instellingen().versleutelsleutel).decrypt(value.encode()).decode()
