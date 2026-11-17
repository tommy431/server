from fastapi import FastAPI

from app.api import aannames, auth, instrumenten, klanten, portefeuilles

app = FastAPI(title="Portefeuille op maat")
app.include_router(auth.router)
app.include_router(instrumenten.router)
app.include_router(klanten.router)
app.include_router(portefeuilles.router)
app.include_router(aannames.router)


@app.get("/gezondheid")
def gezondheid() -> dict:
    return {"status": "ok"}
