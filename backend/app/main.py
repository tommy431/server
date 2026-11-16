from fastapi import FastAPI

from app.api import auth, instrumenten

app = FastAPI(title="Portefeuille op maat")
app.include_router(auth.router)
app.include_router(instrumenten.router)


@app.get("/gezondheid")
def gezondheid() -> dict:
    return {"status": "ok"}
