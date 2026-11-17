import hashlib
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models import Adviseur, Logboek, Portefeuille
from app.security import hash_wachtwoord
from tests.conftest import WACHTWOORD
from tests.test_portefeuille_api import klant_id, pad, vul_koersen  # noqa: F401


@pytest.fixture
def versie(ingelogd, klant_id, db):  # noqa: F811
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    vul_koersen(db, per_jaar=0.05)
    r = ingelogd.post(
        pad(klant_id, "versies"), json={"posities": v["posities"], "overige_kosten_pct": 0.5}
    )
    assert r.status_code == 201
    return r.json()["versie"]


def tekst_van(pdf: bytes, tmp_path) -> str:
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext niet beschikbaar")
    bestand = tmp_path / "r.pdf"
    bestand.write_bytes(pdf)
    return subprocess.run(
        ["pdftotext", "-layout", str(bestand), "-"], capture_output=True, text=True, check=True
    ).stdout


def test_rapport_opstellen_bewaren_en_downloaden(
    ingelogd, klant_id, versie, db, adviseur, tmp_path  # noqa: F811
):
    r = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten")
    assert r.status_code == 201
    meta = r.json()
    assert (
        meta["portefeuille_versie"],
        meta["volgnummer"],
        meta["opgesteld_door"],
        meta["beschikbaar"],
    ) == (
        versie,
        1,
        adviseur.naam,
        True,
    )

    pdf = ingelogd.get(f"/klanten/{klant_id}/rapporten/{meta['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["cache-control"] == "no-store"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) == meta["grootte"]
    assert hashlib.sha256(pdf.content).hexdigest() == meta["sha256"]

    inhoud = tekst_van(pdf.content, tmp_path)
    for verwacht in [
        "Adviesrapport beleggingsportefeuille",
        "Jan Jansen",
        "1. Uw situatie en wensen",
        "2. De voorgestelde portefeuille",
        "iShares Core MSCI World UCITS ETF (Acc)",
        "3. Waarom deze portefeuille bij u past",
        "4. Kosten",
        "Overige kosten",
        "5. Resultaten uit het verleden",
        "In het verleden behaalde resultaten bieden geen garantie voor de toekomst.",
        "6. Mogelijke uitkomsten in de toekomst",
        "Verwacht scenario",
        "geen voorspelling",
        "7. Risico's",
        "Concept: de scenario's in dit rapport rekenen met voorbeeldaannames",
    ]:
        assert verwacht in inhoud, verwacht
    assert "+5,0%" in inhoud  # alle koersen groeien 5% per jaar

    # De PDF staat versleuteld in de database.
    ruw = db.execute(text("select pdf from rapport")).scalar_one()
    assert not bytes(ruw).startswith(b"%PDF") and b"Jan Jansen" not in bytes(ruw)

    tweede = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").json()
    assert tweede["volgnummer"] == 2
    lijst = ingelogd.get(f"/klanten/{klant_id}/rapporten").json()
    assert [x["id"] for x in lijst] == [tweede["id"], meta["id"]]

    acties = db.scalars(
        select(Logboek.actie).where(Logboek.actie.like("rapport_%")).order_by(Logboek.id)
    ).all()
    assert acties == ["rapport_opgesteld", "rapport_gedownload", "rapport_opgesteld"]


def test_rapport_is_een_momentopname(ingelogd, klant_id, versie, db, tmp_path):  # noqa: F811
    eerste = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").json()
    # Later wijzigen koersen en modelallocaties; een nieuw rapport van dezelfde versie blijft gelijk.
    vul_koersen(db, per_jaar=0.20)
    regels = [
        {"categorie": "aandelen", "streef": 20, "minimum": 10, "maximum": 30},
        {"categorie": "obligaties", "streef": 70, "minimum": 60, "maximum": 80},
        {"categorie": "vastgoed", "streef": 5, "minimum": 0, "maximum": 10},
        {"categorie": "grondstoffen", "streef": 0, "minimum": 0, "maximum": 5},
        {"categorie": "liquiditeiten", "streef": 5, "minimum": 0, "maximum": 15},
    ]
    ingelogd.put("/risicoprofielen/neutraal/allocatie", json=regels)
    tweede = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").json()
    a = tekst_van(
        ingelogd.get(f"/klanten/{klant_id}/rapporten/{eerste['id']}/pdf").content, tmp_path
    )
    b = tekst_van(
        ingelogd.get(f"/klanten/{klant_id}/rapporten/{tweede['id']}/pdf").content, tmp_path
    )
    assert "+5,0%" in b and "+20,0%" not in b
    assert "40% – 60%" in b
    assert a == b


def test_onbekende_versie_of_rapport(ingelogd, klant_id, versie):  # noqa: F811
    assert (
        ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/99/rapporten").status_code == 404
    )
    assert ingelogd.get(f"/klanten/{klant_id}/rapporten/999/pdf").status_code == 404


def test_anonimiseren_wist_de_pdf_maar_bewaart_de_vingerafdruk(ingelogd, klant_id, versie, db):  # noqa: F811
    meta = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").json()
    ingelogd.put(f"/klanten/{klant_id}/archief", json={"gearchiveerd": True})
    db.execute(
        Portefeuille.__table__.update().values(
            vastgelegd_op=datetime.now(UTC) - timedelta(days=6 * 365)
        )
    )
    db.commit()
    assert ingelogd.post(f"/klanten/{klant_id}/anonimiseren").status_code == 200
    r = ingelogd.get(f"/klanten/{klant_id}/rapporten/{meta['id']}/pdf")
    assert r.status_code == 410
    lijst = ingelogd.get(f"/klanten/{klant_id}/rapporten").json()
    assert lijst[0]["beschikbaar"] is False and lijst[0]["sha256"] == meta["sha256"]
    assert db.execute(text("select pdf from rapport")).scalar_one() is None
    assert (
        ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").status_code
        == 409
    )


def test_alleen_eigen_klant(client, ingelogd, klant_id, versie, db):  # noqa: F811
    meta = ingelogd.post(f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten").json()
    db.add(
        Adviseur(email="ander@voorbeeld.nl", naam="A", wachtwoord_hash=hash_wachtwoord(WACHTWOORD))
    )
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "ander@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    ander = {"Authorization": f"Bearer {token}"}
    assert (
        client.post(
            f"/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten", headers=ander
        ).status_code
        == 404
    )
    assert client.get(f"/klanten/{klant_id}/rapporten", headers=ander).status_code == 404
    assert (
        client.get(f"/klanten/{klant_id}/rapporten/{meta['id']}/pdf", headers=ander).status_code
        == 404
    )
    assert (
        client.get(
            f"/klanten/{klant_id}/rapporten/{meta['id']}/pdf", headers={"Authorization": ""}
        ).status_code
        == 401
    )
