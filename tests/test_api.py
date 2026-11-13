import json
from contextlib import asynccontextmanager
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.config import Settings
from app.main import app

SERVICE_URL = "https://sap-dev.example/sap/opu/odata/SAP/ZCHAMADOS_DEMO_SRV"
CHAMADO_URL = "/api/v1/chamados?numero=0000000123"
ROW = {
    "__metadata": {"uri": "http://sap-interno.example"},
    "Guid": "12345678-1234-4abc-8def-123456789abc",
    "ObjectId": "0000000123",
    "ProcessType": "Test",
    "Description": "Chamado de teste",
    "CreatedAt": "/Date(1704103200000)/",
    "CreatedBy": "USUARIO_TESTE",
    "ChangedAt": "/Date(1704193200000)/",
    "ChangedBy": "USUARIO_TESTE",
}


@asynccontextmanager
async def api_client(handler, api_token=None, details_entity_set=None, chamados_entity_set="chamadosSet"):
    settings = Settings(
        _env_file=None,
        sap_service_url=SERVICE_URL,
        sap_client="001",
        sap_username=None,
        sap_password=None,
        sap_bearer_token=None,
        sap_chamados_entity_set=chamados_entity_set,
        sap_details_entity_set=details_entity_set,
        api_token=api_token,
    )
    sap_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch("app.main.Settings", return_value=settings),
        patch("app.main.create_http_client", return_value=sap_client),
    ):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                base_url="http://api.local", transport=httpx.ASGITransport(app=app)
            ) as client,
        ):
            yield client


class TestApi(IsolatedAsyncioTestCase):
    async def test_consulta_agrupa_status_entre_paginas(self):
        def sap(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.host, "sap-dev.example")
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.path, httpx.URL(SERVICE_URL).path + "/chamadosSet")
            self.assertEqual(request.url.params["sap-client"], "001")
            if "$skiptoken" in request.url.params:
                return httpx.Response(200, json={"d": {"results": [
                    {**ROW, "Stat": "E9002", "Txt30": "Prazo de teste excedido"},
                    {**ROW, "Stat": "I9001", "Txt30": ""},
                    {**ROW, "Stat": "I9002", "Txt30": ""},
                ]}})

            self.assertEqual(request.url.params["$filter"], "ObjectId eq '0000000123'")
            self.assertEqual(request.url.params["$format"], "json")
            self.assertIn(b"ObjectId%20eq%20'0000000123'", request.url.query)
            return httpx.Response(200, json={"d": {
                "results": [
                    {**ROW, "Stat": "E9001", "Txt30": "Em Desenvolvimento"},
                    {**ROW, "Stat": "E9002", "Txt30": ""},
                ],
                "__next": "http://sap-interno.example" + request.url.path + "?$skiptoken=2",
            }})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)

        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        self.assertEqual(chamado["numero"], "0000000123")
        self.assertEqual(chamado["criado_em"], "2024-01-01T10:00:00Z")
        self.assertNotIn("__metadata", chamado)
        self.assertIsNone(chamado["parceiros"])
        self.assertIsNone(chamado["referencias_externas"])
        self.assertIsNone(chamado["textos"])
        self.assertEqual(chamado["status"], [
            {"codigo": "E9001", "descricao": "Em Desenvolvimento"},
            {"codigo": "E9002", "descricao": "Prazo de teste excedido"},
            {"codigo": "I9001", "descricao": None},
            {"codigo": "I9002", "descricao": None},
        ])

    async def test_carrega_detalhes_uma_vez_por_guid(self):
        requisicoes_detalhes = []
        cabecalho = {**ROW, "CreatedAt": "20240101100000", "ChangedAt": "20240102110000"}
        detalhes = {
            "status": [{"codigo": "I9001", "descricao": "Status do sistema"}],
            "parceiros": [
                {"funcao": "Z001", "descricao": "Consultor", "numero_bp": "0010", "nome": "Pessoa Teste"},
            ],
            "referencias_externas": [{"tipo": "EXT", "descricao": "Referência", "numero": "EXT001"}],
            "textos": [
                {"tipo": "Z001", "idioma": "P", "linhas": [{"formato": "*", "texto": "Descrição do chamado"}]},
            ],
        }

        def sap(request):
            if request.url.path.endswith("/ChamadoSet"):
                self.assertEqual(request.url.params["$filter"], "ObjectId eq '0000000123'")
                return httpx.Response(200, json={"d": {"results": [
                    {**cabecalho, "Stat": "E9001"},
                    {**cabecalho, "Stat": "I9001"},
                ]}})

            requisicoes_detalhes.append(request)
            self.assertTrue(request.url.path.endswith(f"/DetalheChamadoSet(guid'{ROW['Guid'].upper()}')"))
            self.assertEqual(request.url.params["sap-client"], "001")
            self.assertEqual(request.url.params["$format"], "json")
            return httpx.Response(200, json={"d": {
                "Guid": ROW["Guid"].upper(),
                "DadosJson": json.dumps(detalhes),
            }})

        async with api_client(sap, details_entity_set="DetalheChamadoSet", chamados_entity_set="ChamadoSet") as client:
            resposta = await client.get(CHAMADO_URL)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(requisicoes_detalhes), 1)
        (chamado,) = resposta.json()["chamados"]
        self.assertEqual(chamado["criado_em"], "2024-01-01T10:00:00Z")
        self.assertEqual(chamado["atualizado_em"], "2024-01-02T11:00:00Z")
        for campo, valor in detalhes.items():
            self.assertEqual(chamado[campo], valor)

    async def test_chamado_inexistente(self):
        async with api_client(lambda _: httpx.Response(200, json={"d": {"results": []}})) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"chamados": []})

    async def test_rejeita_resultado_fora_do_filtro(self):
        def sap(_):
            return httpx.Response(200, json={"d": {"results": [{**ROW, "ObjectId": "9"}]}})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn("fora do filtro", resposta.json()["detail"])

    async def test_rejeita_redirecionamento_para_login(self):
        def sap(request):
            self.assertEqual(request.url.host, "sap-dev.example")
            return httpx.Response(302, headers={"Location": "https://login.example/saml2"})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn("redirecionou", resposta.json()["detail"])

    async def test_retorna_504_quando_sap_expira(self):
        def sap(request):
            raise httpx.ReadTimeout("timeout", request=request)

        async with api_client(sap) as client:
            self.assertEqual((await client.get(CHAMADO_URL)).status_code, 504)

    async def test_valida_numero_antes_de_consultar_sap(self):
        def sap(_):
            self.fail("O SAP não deve receber um número inválido")

        async with api_client(sap) as client:
            resposta = await client.get("/api/v1/chamados?numero=invalido")
        self.assertEqual(resposta.status_code, 422)

    async def test_exige_token_quando_configurado(self):
        async with api_client(
            lambda _: httpx.Response(200, json={"d": {"results": []}}), api_token="token-teste"
        ) as client:
            sem_token = await client.get(CHAMADO_URL)
            com_token = await client.get(CHAMADO_URL, headers={"Authorization": "Bearer token-teste"})
        self.assertEqual(sem_token.status_code, 401)
        self.assertEqual(com_token.status_code, 200)
