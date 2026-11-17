from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import instellingen


class Basis(DeclarativeBase):
    # Dezelfde namen die PostgreSQL zelf zou kiezen, zodat elke beperking een vaste naam heeft en
    # migraties ze ook weer kunnen verwijderen.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "%(table_name)s_%(column_0_N_name)s_key",
            "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
            "pk": "%(table_name)s_pkey",
        }
    )


@lru_cache
def engine() -> Engine:
    return create_engine(instellingen().database_url, pool_pre_ping=True)


def sessie() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s
