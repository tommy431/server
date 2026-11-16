from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Instellingen(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://portefeuille:portefeuille@localhost:5432/portefeuille"
    # Verplicht en zonder standaardwaarde: een geraden sleutel maakt elk token vervalsbaar.
    jwt_geheim: str
    token_geldigheid_minuten: int = 480
    max_mislukte_logins: int = 5
    login_blokkade_minuten: int = 15


@lru_cache
def instellingen() -> Instellingen:
    return Instellingen()
