"""Productie: één server voor de API (onder /api) en de gebouwde schermen.

Start met: uvicorn app.productie:app --host 0.0.0.0 --port 8000 --proxy-headers
Zet er een proxy met HTTPS voor; de server zelf spreekt alleen HTTP.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from app.main import app as api

SCHERMEN = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

BEVEILIGINGSHEADERS = {
    # Alleen eigen scripts; inline stijlen zijn nodig voor de breedtes van grafieken en balken.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
        "form-action 'self'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

app = FastAPI(title="Portefeuille op maat", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def beveiligingsheaders(request: Request, volgende):
    antwoord = await volgende(request)
    antwoord.headers.update(BEVEILIGINGSHEADERS)
    if request.url.path.startswith("/api/"):
        # Antwoorden met klantgegevens niet in tussenliggende of browsercaches bewaren.
        antwoord.headers.setdefault("Cache-Control", "no-store")
    return antwoord


app.mount("/api", api)


@app.get("/{pad:path}", include_in_schema=False)
def schermen(pad: str) -> FileResponse:
    """Levert de gebouwde schermen; onbekende paden krijgen index.html (de app regelt de routes)."""
    if not (SCHERMEN / "index.html").is_file():
        raise HTTPException(
            503, "De schermen zijn niet gebouwd; voer 'npm run build' uit in frontend/"
        )
    bestand = (SCHERMEN / pad).resolve()
    if pad and bestand.is_file() and bestand.is_relative_to(SCHERMEN):
        # Bestanden in assets/ hebben een inhoudshash in de naam en mogen lang in de cache.
        cache = "public, max-age=31536000, immutable" if pad.startswith("assets/") else "no-cache"
        return FileResponse(bestand, headers={"Cache-Control": cache})
    return FileResponse(SCHERMEN / "index.html", headers={"Cache-Control": "no-cache"})
