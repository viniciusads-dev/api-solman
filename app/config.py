from pathlib import Path
from typing import Annotated

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NomeColecaoSap = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    sap_service_url: HttpUrl
    sap_client: Annotated[str, Field(pattern=r"^[0-9]{3}$")] | None = None
    sap_username: str | None = None
    sap_password: SecretStr | None = None
    sap_bearer_token: SecretStr | None = None
    sap_ca_file: Path | None = None
    sap_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 15
    sap_chamados_entity_set: NomeColecaoSap = "chamadosSet"
    sap_details_entity_set: NomeColecaoSap | None = None
    api_token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_connection_settings(self) -> "Settings":
        url = self.sap_service_url
        if any(
            part is not None for part in (url.username, url.password, url.query, url.fragment)
        ):
            raise ValueError("SAP_SERVICE_URL deve conter somente o endereço do serviço")
        last_segment = (url.path or "").rstrip("/").rsplit("/", 1)[-1]
        if last_segment in {"$metadata", self.sap_chamados_entity_set, self.sap_details_entity_set}:
            raise ValueError("SAP_SERVICE_URL deve apontar para a raiz do serviço OData")
        if bool(self.sap_username) != bool(self.sap_password):
            raise ValueError("Preencha SAP_USERNAME e SAP_PASSWORD juntos")
        if self.sap_bearer_token and self.sap_username:
            raise ValueError("Use somente um método de autenticação no SAP")
        return self
