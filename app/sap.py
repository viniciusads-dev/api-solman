import asyncio
import ssl
from urllib.parse import quote, urlencode
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import Chamado, DetalhesChamado, SapResposta, SapRespostaDetalhe, StatusChamado


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
        details_entity_set = settings.sap_details_entity_set
        self._details = httpx.URL(f"{service_url}/{details_entity_set}") if details_entity_set else None
        self._mandante = settings.sap_client
        self._timeout = settings.sap_timeout_seconds

    async def consultar(self, numero: str) -> list[Chamado]:
        params = {"$filter": f"ObjectId eq '{numero}'", "$format": "json"}
        if self._mandante:
            params["sap-client"] = self._mandante

        query = urlencode(params, safe="$'", quote_via=quote).encode("ascii")
        url = self._collection.copy_with(query=query)
        visitadas: set[httpx.URL] = set()
        chamados: dict[UUID, Chamado] = {}

        async with asyncio.timeout(self._timeout):
            while url not in visitadas:
                visitadas.add(url)
                pagina = await self._carregar_pagina(url)
                for linha in pagina.d.results:
                    if linha.numero != numero:
                        raise SapError("O SAP retornou um registro fora do filtro solicitado.")

                    chamado = chamados.get(linha.guid)
                    if chamado is None:
                        chamado = Chamado.model_validate(linha, from_attributes=True)
                        chamados[linha.guid] = chamado

                    if linha.codigo_status:
                        descricao = (linha.descricao_status or "").strip() or None
                        status = next(
                            (item for item in chamado.status if item.codigo == linha.codigo_status),
                            None,
                        )
                        if status is None:
                            chamado.status.append(
                                StatusChamado(codigo=linha.codigo_status, descricao=descricao)
                            )
                        elif status.descricao is None:
                            status.descricao = descricao

                if not pagina.d.proxima:
                    if self._details is not None:
                        for chamado in chamados.values():
                            detalhes = await self._carregar_detalhes(self._details, chamado.guid)
                            chamado.status = detalhes.status
                            chamado.parceiros = detalhes.parceiros
                            chamado.referencias_externas = detalhes.referencias_externas
                            chamado.textos = detalhes.textos
                    return list(chamados.values())
                url = self._continuacao(url, pagina.d.proxima)

        raise SapError("O SAP repetiu uma página da consulta.")

    def _continuacao(self, atual: httpx.URL, link: str) -> httpx.URL:
        try:
            destino = atual.join(link)
        except (httpx.InvalidURL, ValueError) as error:
            raise SapError("O SAP retornou um link de paginação inválido.") from error
        if destino.path != self._collection.path or not destino.query:
            raise SapError("O SAP retornou um link de paginação inválido.")

        # O Gateway pode anunciar seu host interno mesmo atrás de um proxy HTTPS.
        query = destino.query
        if self._mandante:
            mandantes = destino.params.get_list("sap-client")
            if not mandantes:
                query += f"&sap-client={self._mandante}".encode("ascii")
            elif mandantes != [self._mandante]:
                raise SapError("O SAP retornou uma página de outro mandante.")
        return self._collection.copy_with(query=query)

    async def _carregar_pagina(self, url: httpx.URL) -> SapResposta:
        conteudo = await self._get_odata(url)
        try:
            return SapResposta.model_validate_json(conteudo)
        except ValidationError as error:
            raise SapError("O SAP não retornou o JSON OData esperado. Confira a URL e o login.") from error

    async def _carregar_detalhes(self, colecao: httpx.URL, guid: UUID) -> DetalhesChamado:
        params = {"$format": "json"}
        if self._mandante:
            params["sap-client"] = self._mandante
        chave = str(guid).upper()
        url = colecao.copy_with(path=f"{colecao.path}(guid'{chave}')").copy_merge_params(params)

        conteudo = await self._get_odata(url)
        try:
            resposta = SapRespostaDetalhe.model_validate_json(conteudo)
        except ValidationError as error:
            raise SapError("O SAP não retornou os detalhes no formato esperado.") from error
        if resposta.d.guid != guid:
            raise SapError("O SAP retornou os detalhes de outro chamado.")
        return resposta.d.dados

    async def _get_odata(self, url: httpx.URL) -> bytes:
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
        if not resposta.is_success:
            raise SapError(f"O SAP respondeu com HTTP {resposta.status_code}.")

        return resposta.content
