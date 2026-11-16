from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import instellingen


class Basis(DeclarativeBase):
    pass


@lru_cache
def engine() -> Engine:
    return create_engine(instellingen().database_url, pool_pre_ping=True)


def sessie() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s
