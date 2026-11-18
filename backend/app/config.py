from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import field_validator
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
    # Blokkade na mislukte inlogpogingen binnen `login_blokkade_minuten`:
    # per combinatie van IP-adres en account (een aanvaller elders sluit de gebruiker niet buiten),
    max_mislukte_logins: int = 5
    # per IP-adres over alle accounts (tegen het proberen van veel accounts),
    max_mislukte_logins_per_ip: int = 20
    # en per account over alle IP-adressen (alleen bij een grootschalige aanval).
    max_mislukte_logins_per_account: int = 50
    # Algemene limiet op het aantal verzoeken per IP-adres per minuut; 0 schakelt hem uit.
    # Ruim gekozen, omdat een kantoor vaak met één IP-adres naar buiten gaat.
    limiet_verzoeken_per_minuut: int = 1200
    # Koersen van overig bezit (buiten de fondsenlijst) ophalen bij Yahoo; uit in testomgevingen.
    marktkoersen_ophalen: bool = True

    @field_validator("jwt_geheim")
    @classmethod
    def _sterk_geheim(cls, waarde: str) -> str:
        if len(waarde) < 32:
            raise ValueError("JWT_GEHEIM moet minstens 32 tekens lang zijn")
        return waarde

    @field_validator("versleutelsleutel")
    @classmethod
    def _geldige_sleutel(cls, waarde: str) -> str:
        try:
            Fernet(waarde)
        except (ValueError, TypeError) as fout:
            raise ValueError(
                "VERSLEUTELSLEUTEL is geen geldige sleutel; maak er een met "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            ) from fout
        return waarde

    login_blokkade_minuten: int = 15


@lru_cache
def instellingen() -> Instellingen:
    return Instellingen()
