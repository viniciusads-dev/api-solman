import asyncio
import ssl
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import Chamado, SapResposta

SAP_CHAMADO_INEXISTENTE = "/IWBEP/CM_MGW_RT/020"


class SapError(Exception):
    pass


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    tls = ssl.create_default_context()
    if settings.sap_ca_file:
        tls.load_verify_locations(cafile=settings.sap_ca_file)

    headers = {"Accept": "application/json"}
    auth = None
    if settings.sap_username and settings.sap_password:
        auth = httpx.BasicAuth(settings.sap_username, settings.sap_password.get_secret_value())
    if settings.sap_bearer_token:
        headers["Authorization"] = f"Bearer {settings.sap_bearer_token.get_secret_value()}"

    return httpx.AsyncClient(
        auth=auth,
        headers=headers,
        verify=tls,
        follow_redirects=False,
        timeout=settings.sap_timeout_seconds,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )


class SapGateway:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        service_url = str(settings.sap_service_url).rstrip("/")
        self._collection = httpx.URL(f"{service_url}/{settings.sap_chamados_entity_set}")
        self._mandante = settings.sap_client
        self._timeout = settings.sap_timeout_seconds

    async def consultar(self, numero: str) -> list[Chamado]:
        params = {"$format": "json"}
        if self._mandante:
            params["sap-client"] = self._mandante

        query = urlencode(params, safe="$").encode("ascii")
        url = httpx.URL(f"{self._collection}('{numero}')", query=query)
        async with asyncio.timeout(self._timeout):
            conteudo = await self._get_odata(url)
        if conteudo is None:
            return []

        try:
            resposta = SapResposta.model_validate_json(conteudo)
        except ValidationError as error:
            raise SapError(
                "O SAP não retornou o chamado completo no formato OData esperado."
            ) from error
        if resposta.d.numero != numero:
            raise SapError("O SAP retornou um chamado com ObjectId diferente do solicitado.")
        return [Chamado.model_validate(resposta.d.model_dump())]

    async def _get_odata(self, url: httpx.URL) -> bytes | None:
        try:
            resposta = await self._client.get(url)
        except httpx.TimeoutException as error:
            raise TimeoutError from error
        except httpx.RequestError as error:
            raise SapError("Falha na conexão com o SAP. Confira a URL, a rede e o certificado.") from error

        if resposta.is_redirect:
            raise SapError("O SAP redirecionou a chamada. Confirme com o Basis a URL de integração.")
        if resposta.status_code in (401, 403):
            raise SapError(
                f"O SAP recusou o acesso ({resposta.status_code}). "
                "Confira a autenticação e as permissões."
            )
        if resposta.status_code == 404:
            try:
                payload = resposta.json()
            except ValueError:
                payload = None
            erro = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(erro, dict) and erro.get("code") == SAP_CHAMADO_INEXISTENTE:
                return None
        if not resposta.is_success:
            raise SapError(f"O SAP respondeu com HTTP {resposta.status_code}.")

        return resposta.content
