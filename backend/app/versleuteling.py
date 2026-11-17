from cryptography.fernet import Fernet
from sqlalchemy import LargeBinary, Text
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


class VersleuteldeBytes(TypeDecorator):
    """Binaire kolom (bijv. een PDF) die versleuteld in de database staat."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return Fernet(instellingen().versleutelsleutel).encrypt(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Fernet(instellingen().versleutelsleutel).decrypt(value)
