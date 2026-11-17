"""Algemene limiet op het aantal verzoeken per IP-adres, tegen overbelasting.

Telt in het geheugen van één serverproces. Bij meerdere processen geldt de limiet per proces;
voor een harde limiet over alle processen is een gedeelde opslag (zoals Redis) nodig.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import instellingen

VENSTER = 60.0
UITGEZONDERD = {"/gezondheid"}


class Verzoeklimiet(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._verzoeken: dict[str, deque[float]] = defaultdict(deque)
        self._slot = Lock()
        self._laatst_opgeruimd = time.monotonic()

    def _toegestaan(self, ip: str, limiet: int) -> bool:
        nu = time.monotonic()
        with self._slot:
            if nu - self._laatst_opgeruimd > VENSTER:
                # IP-adressen zonder recente verzoeken vergeten, zodat het geheugen niet groeit.
                for sleutel in [
                    k for k, v in self._verzoeken.items() if not v or nu - v[-1] > VENSTER
                ]:
                    del self._verzoeken[sleutel]
                self._laatst_opgeruimd = nu
            tijden = self._verzoeken[ip]
            while tijden and nu - tijden[0] > VENSTER:
                tijden.popleft()
            if len(tijden) >= limiet:
                return False
            tijden.append(nu)
            return True

    async def dispatch(self, request: Request, volgende):
        limiet = instellingen().limiet_verzoeken_per_minuut
        if limiet and request.url.path not in UITGEZONDERD:
            ip = request.client.host if request.client else "onbekend"
            if not self._toegestaan(ip, limiet):
                return JSONResponse(
                    {"detail": "Te veel verzoeken; probeer het over een minuut opnieuw"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        return await volgende(request)
