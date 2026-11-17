# Productie-image: bouwt de schermen en draait API en schermen op één poort.
# Bouwen:  docker build -t portefeuille .
# Starten: docker run -p 8000:8000 --env-file backend/.env portefeuille
#          (DATABASE_URL, JWT_GEHEIM en VERSLEUTELSLEUTEL zijn verplicht)

FROM node:22-slim AS schermen
WORKDIR /bouw/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS server
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN rm -f .env e2e-test.db && uv sync --locked --no-dev
COPY --from=schermen /bouw/frontend/dist /app/frontend/dist

# Niet als root draaien.
RUN useradd --system --uid 10001 portefeuille && chown -R portefeuille /app
USER portefeuille
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/gezondheid')"
# Alleen het IP-adres van de eigen proxy vertrouwen voor X-Forwarded-For. Met '*' kan iedereen een
# vals IP-adres meesturen en zo de inlog- en verzoeklimieten omzeilen.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
# Eerst migreren, dan starten. Achter een proxy met HTTPS.
# Rechtstreeks uit de virtuele omgeving; uv is bij het starten niet nodig (en heeft geen
# schrijfbare thuismap voor deze gebruiker).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.productie:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
