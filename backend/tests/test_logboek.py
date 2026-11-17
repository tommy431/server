import itertools

from sqlalchemy import delete, select, text

from app.logboek import BEGIN, controleer_keten, leg_vast
from app.models import Logboek, LogboekKop


def vul(db, n=5):
    for i in range(n):
        leg_vast(db, "test", entiteit="x", entiteit_id=i, details={"nummer": i, "tekst": "é€"})
    db.commit()


def test_keten_is_in_orde_en_rijgt_regels_aan_elkaar(db):
    vul(db)
    regels = db.scalars(select(Logboek).order_by(Logboek.id)).all()
    assert regels[0].vorige_hash == BEGIN
    assert all(b.vorige_hash == a.hash for a, b in itertools.pairwise(regels))
    c = controleer_keten(db)
    assert (c.in_orde, c.aantal, c.laatste_hash) == (True, 5, regels[-1].hash)
    assert db.get(LogboekKop, 1).laatste_id == regels[-1].id


def test_gewijzigde_inhoud_wordt_ontdekt(db):
    vul(db)
    db.execute(
        text("update logboek set details = :d where entiteit_id = '2'"), {"d": '{"nummer": 99}'}
    )
    db.commit()
    db.expire_all()
    c = controleer_keten(db)
    assert not c.in_orde and c.fout == "De inhoud van deze regel is gewijzigd"
    assert db.get(Logboek, c.fout_bij).entiteit_id == "2"


def test_gewijzigd_tijdstip_of_persoon_wordt_ontdekt(db):
    vul(db)
    db.execute(
        text("update logboek set adviseur_id = NULL, actie = 'anders' where entiteit_id = '1'")
    )
    db.commit()
    db.expire_all()
    assert not controleer_keten(db).in_orde


def test_verwijderde_regel_wordt_ontdekt(db):
    vul(db)
    db.execute(delete(Logboek).where(Logboek.entiteit_id == "2"))
    db.commit()
    c = controleer_keten(db)
    assert not c.in_orde and "verwijderd of ingevoegd" in c.fout


def test_verwijderde_laatste_regels_worden_ontdekt(db):
    vul(db)
    db.execute(delete(Logboek).where(Logboek.entiteit_id.in_(["3", "4"])))
    db.commit()
    c = controleer_keten(db)
    assert not c.in_orde and "aan het eind" in c.fout


def test_api_alleen_voor_beheerders(ingelogd, client, db):
    vul(db, 3)
    regels = ingelogd.get("/logboek", params={"actie": "test"}).json()
    assert [r["entiteit_id"] for r in regels] == ["2", "1", "0"]
    ouder = ingelogd.get("/logboek", params={"voor_id": regels[0]["id"], "actie": "test"}).json()
    assert [r["entiteit_id"] for r in ouder] == ["1", "0"]
    c = ingelogd.get("/logboek/controle").json()
    assert c["in_orde"] is True and c["aantal"] >= 4  # plus de login van de beheerder
    assert client.get("/logboek", headers={"Authorization": ""}).status_code == 401
