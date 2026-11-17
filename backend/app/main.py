from fastapi import FastAPI

from app.api import (
    aannames,
    adviseurs,
    auth,
    instrumenten,
    klanten,
    logboek,
    onderneming,
    portefeuilles,
    rapporten,
    wijzigingen,
)

app = FastAPI(title="Portefeuille op maat")
app.include_router(auth.router)
app.include_router(instrumenten.router)
app.include_router(klanten.router)
app.include_router(portefeuilles.router)
app.include_router(aannames.router)
app.include_router(rapporten.router)
app.include_router(wijzigingen.router)
app.include_router(onderneming.router)
app.include_router(adviseurs.router)
app.include_router(logboek.router)


@app.get("/gezondheid")
def gezondheid() -> dict:
    return {"status": "ok"}
