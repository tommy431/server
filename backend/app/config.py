from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Instellingen(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://portefeuille:portefeuille@localhost:5432/portefeuille"
    # Verplicht en zonder standaardwaarde: een geraden sleutel maakt elk token vervalsbaar.
    jwt_geheim: str
    # Fernet-sleutel voor het versleutelen van persoonsgegevens. Verlies van de sleutel maakt
    # de klantgegevens onleesbaar: bewaar hem buiten de database.
    versleutelsleutel: str
    # Vier-ogenprincipe: wijzigingen van modelallocaties en aannames vereisen goedkeuring door een
    # tweede beheerder. Alleen uitzetten als er maar één beheerder is.
    vier_ogen: bool = True
    # Beheerders moeten tweestapsverificatie gebruiken voordat ze beheertaken kunnen doen.
    tweestaps_verplicht_beheerder: bool = True
    token_geldigheid_minuten: int = 480
    max_mislukte_logins: int = 5
    login_blokkade_minuten: int = 15


@lru_cache
def instellingen() -> Instellingen:
    return Instellingen()
