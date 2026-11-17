import pytest
from fastapi.testclient import TestClient

from app.db import sessie
from app.main import app as api
from app.productie import SCHERMEN, app
from tests.conftest import WACHTWOORD


@pytest.fixture
def prod(db):
    api.dependency_overrides[sessie] = lambda: db
    yield TestClient(app)
    api.dependency_overrides.clear()


def test_api_onder_api_met_beveiligingsheaders(prod, adviseur):
    r = prod.post("/api/auth/login", json={"email": adviseur.email, "wachtwoord": WACHTWOORD})
    assert r.status_code == 200
    for kop in [
        "Content-Security-Policy",
        "X-Frame-Options",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
    ]:
        assert kop in r.headers
    assert r.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    # Geen openbare API-documentatie in productie.
    assert (
        prod.get("/api/docs").status_code in (404, 200)
        and "swagger" not in prod.get("/docs").text.lower()
    )


@pytest.mark.skipif(not (SCHERMEN / "index.html").is_file(), reason="schermen niet gebouwd")
def test_schermen_en_terugval_op_index(prod):
    hoofd = prod.get("/")
    assert hoofd.status_code == 200 and '<div id="root">' in hoofd.text
    assert hoofd.headers["Cache-Control"] == "no-cache"
    # Een route van de app (bijv. na herladen) geeft ook index.html.
    assert '<div id="root">' in prod.get("/klanten/12/portefeuille").text
    asset = next((SCHERMEN / "assets").glob("*.js")).name
    r = prod.get(f"/assets/{asset}")
    assert r.status_code == 200 and "immutable" in r.headers["Cache-Control"]


@pytest.mark.skipif(not (SCHERMEN / "index.html").is_file(), reason="schermen niet gebouwd")
def test_geen_bestanden_buiten_de_schermenmap(prod):
    for pad in ["/../backend/.env", "/..%2F..%2Fbackend%2F.env", "/%2e%2e/%2e%2e/etc/passwd"]:
        r = prod.get(pad)
        assert "JWT_GEHEIM" not in r.text and "root:" not in r.text
        assert '<div id="root">' in r.text or r.status_code == 404
