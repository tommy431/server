import os

os.environ["JWT_GEHEIM"] = "test-geheim-alleen-voor-de-testsuite-0123456789"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Basis, sessie
from app.main import app
from app.models import Adviseur
from app.security import hash_wachtwoord

WACHTWOORD = "een-lang-testwachtwoord"


@pytest.fixture
def db():
    # Standaard SQLite in het geheugen; zet TEST_DATABASE_URL om tegen PostgreSQL te testen.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Basis.metadata.drop_all(engine)
    Basis.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    Basis.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def adviseur(db):
    a = Adviseur(
        email="adviseur@voorbeeld.nl",
        naam="Test Adviseur",
        wachtwoord_hash=hash_wachtwoord(WACHTWOORD),
    )
    db.add(a)
    db.commit()
    return a


@pytest.fixture
def client(db):
    app.dependency_overrides[sessie] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def ingelogd(client, adviseur):
    token = client.post(
        "/auth/login", json={"email": adviseur.email, "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


UNIVERSUM_KOP = (
    "isin,ticker,naam,categorie,regio,sector,valuta,lopende_kosten,"
    "kosten_geverifieerd,uitkerend,startdatum\n"
)
UNIVERSUM = (
    UNIVERSUM_KOP
    + "IE00B4L5Y983,IWDA.AS,Wereld,aandelen,wereld,breed,EUR,0.20,nee,nee,2009-09-25\n"
    + "IE00B4WXJJ64,IEGA.AS,Staatsobligaties,obligaties,europa,breed,EUR,0.07,ja,ja,\n"
)
