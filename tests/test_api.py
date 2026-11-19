import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.main import app

SERVICE_URL = "https://sap-dev.example/sap/opu/odata/SAP/SERVICO_TESTE"
ENTITY_SET = "ColecaoUnificadaTeste"
CHAMADO_URL = "/api/v1/chamados?numero=0000000123"
LOG = "  Descrição\r\n13.11.2026          09:33:31\u00a0\u00a0TESTE\n\nCriação do chamado  \n"
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
    "Status": "NEW (Novo)",
    "ConsultorFuncional": "Consultor de teste",
    "DesenvolvedorAbap": "Desenvolvedor de teste",
    "ReferenciasExternas": "250728-1",
    "Textos": LOG,
    "Estimativa": "1234567.891",
    "DtIniDesenv": "20261123130000",
    "DtFimDesenv": "20261125210000",
    "DtDesejCliente": "20261126000000",
}


@asynccontextmanager
async def api_client(handler, api_token=None, entity_set=ENTITY_SET, sap_client="001", timeout=15):
    settings = Settings(
        _env_file=None,
        sap_service_url=SERVICE_URL,
        sap_client=sap_client,
        sap_username=None,
        sap_password=None,
        sap_bearer_token=None,
        sap_chamados_entity_set=entity_set,
        sap_timeout_seconds=timeout,
        api_token=api_token,
    )
    sap_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch("app.main.Settings", return_value=settings),
        patch("app.main.create_http_client", return_value=sap_http),
    ):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                base_url="http://api.local", transport=httpx.ASGITransport(app=app)
            ) as client,
        ):
            yield client


class TestApi(IsolatedAsyncioTestCase):
    async def test_consulta_completa_em_um_unico_get_por_chave(self):
        requisicoes = []

        def sap(request):
            requisicoes.append(request)
            return httpx.Response(200, json={"d": ROW})

        async with api_client(sap, entity_set="NomeDefinidoPeloSap") as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(len(requisicoes), 1)
        (request,) = requisicoes
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.host, "sap-dev.example")
        self.assertEqual(request.url.scheme, "https")
        self.assertEqual(
            request.url.path, httpx.URL(SERVICE_URL).path + "/NomeDefinidoPeloSap('0000000123')"
        )
        self.assertEqual(dict(request.url.params), {"$format": "json", "sap-client": "001"})
        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        self.assertEqual(chamado, {
            "guid": ROW["Guid"], "numero": "0000000123", "descricao": ROW["Description"],
            "tipo_processo": "Test", "criado_em": "2024-01-01T10:00:00Z",
            "criado_por": "USUARIO_TESTE", "atualizado_em": "2024-01-02T11:00:00Z",
            "atualizado_por": "USUARIO_TESTE", "status": ROW["Status"],
            "consultor_funcional": ROW["ConsultorFuncional"],
            "desenvolvedor_abap": ROW["DesenvolvedorAbap"],
            "numero_externo": "250728-1", "textos": LOG, "estimativa": "1234567.891",
            "data_inicio_desenvolvimento": "20261123130000",
            "data_fim_desenvolvimento": "20261125210000",
            "data_desejada_cliente": "20261126000000",
        })

    async def test_campos_vazios(self):
        linha = {
            **ROW, "CreatedAt": "0", "ChangedAt": "", "Status": "", "ConsultorFuncional": "",
            "DesenvolvedorAbap": "", "ReferenciasExternas": "", "Textos": "",
            "Estimativa": "0.000", "DtIniDesenv": "0", "DtFimDesenv": 0, "DtDesejCliente": None,
        }
        async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
            resposta = await client.get(CHAMADO_URL)

        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        self.assertIsNone(chamado["criado_em"])
        self.assertIsNone(chamado["atualizado_em"])
        self.assertIsNone(chamado["numero_externo"])
        for campo in ("status", "consultor_funcional", "desenvolvedor_abap", "textos"):
            self.assertEqual(chamado[campo], "")
        self.assertEqual(chamado["estimativa"], "0.000")
        for campo in ("data_inicio_desenvolvimento", "data_fim_desenvolvimento", "data_desejada_cliente"):
            self.assertIsNone(chamado[campo])

    async def test_aceita_resposta_sem_campos_de_planejamento(self):
        linha = dict(ROW)
        for campo in ("Estimativa", "DtIniDesenv", "DtFimDesenv", "DtDesejCliente"):
            del linha[campo]
        async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
            resposta = await client.get(CHAMADO_URL)

        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        for campo in ("estimativa", "data_inicio_desenvolvimento", "data_fim_desenvolvimento", "data_desejada_cliente"):
            self.assertIsNone(chamado[campo])

    async def test_formata_datas_planejadas_odata_em_dia_mes_ano(self):
        linha = {
            **ROW,
            "Estimativa": "1234567890.123",
            "DtIniDesenv": "/Date(1794960000000)/",
            "DtFimDesenv": "/Date(1795046400000)/",
            "DtDesejCliente": "/Date(1795132800000)/",
        }
        async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
            resposta = await client.get(CHAMADO_URL)

        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        self.assertEqual(chamado["estimativa"], "1234567890.123")
        self.assertEqual(chamado["data_inicio_desenvolvimento"], "18-11-2026")
        self.assertEqual(chamado["data_fim_desenvolvimento"], "19-11-2026")
        self.assertEqual(chamado["data_desejada_cliente"], "20-11-2026")
        self.assertEqual(chamado["textos"], LOG)

    async def test_converte_timestamp_sap_decimal(self):
        linha = {**ROW, "CreatedAt": "20240101100000.1234567", "ChangedAt": 20240102110000}
        async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 200)
        (chamado,) = resposta.json()["chamados"]
        self.assertEqual(chamado["criado_em"], "2024-01-01T10:00:00.123456Z")
        self.assertEqual(chamado["atualizado_em"], "2024-01-02T11:00:00Z")

    async def test_chamado_inexistente(self):
        requisicoes = []

        def sap(request):
            requisicoes.append(request)
            return httpx.Response(404, json={"error": {"code": "/IWBEP/CM_MGW_RT/020"}})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(resposta.json(), {"detail": "Chamado não encontrado."})
        self.assertEqual(len(requisicoes), 1)

    async def test_rejeita_object_id_diferente_do_solicitado(self):
        linha = {**ROW, "ObjectId": "9"}
        async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn("ObjectId diferente", resposta.json()["detail"])

    async def test_rejeita_envelope_da_colecao_sem_segunda_requisicao(self):
        requisicoes = []

        def sap(request):
            requisicoes.append(request)
            return httpx.Response(200, json={"d": {
                "results": [ROW], "__next": "https://outro.example/colecao?$skiptoken=2",
            }})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn("formato OData esperado", resposta.json()["detail"])
        self.assertEqual(len(requisicoes), 1)

    async def test_rejeita_detalhes_ausentes_ou_fora_do_tipo(self):
        for campo in ("Status", "ConsultorFuncional", "DesenvolvedorAbap", "ReferenciasExternas", "Textos"):
            casos = ({k: v for k, v in ROW.items() if k != campo}, {**ROW, campo: None}, {**ROW, campo: []})
            for linha in casos:
                with self.subTest(campo=campo, valor=linha.get(campo, "ausente")):
                    async with api_client(lambda _: httpx.Response(200, json={"d": linha})) as client:
                        resposta = await client.get(CHAMADO_URL)
                    self.assertEqual(resposta.status_code, 502)
                    self.assertIn("formato OData esperado", resposta.json()["detail"])

    async def test_rejeita_json_odata_invalido(self):
        for conteudo in (b"<html>login</html>", b'{}', b'{"d":{"results":null}}'):
            with self.subTest(conteudo=conteudo):
                async with api_client(lambda _: httpx.Response(200, content=conteudo)) as client:
                    self.assertEqual((await client.get(CHAMADO_URL)).status_code, 502)

    async def test_rejeita_redirecionamento_sem_seguir_login(self):
        requisicoes = []

        def sap(request):
            requisicoes.append(request)
            return httpx.Response(302, headers={"Location": "https://login.example/saml2"})

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn("redirecionou", resposta.json()["detail"])
        self.assertEqual(len(requisicoes), 1)

    async def test_trata_erro_http_sap(self):
        for status in (401, 403, 404, 500):
            with self.subTest(status=status):
                async with api_client(lambda _: httpx.Response(status, text="conteúdo interno")) as client:
                    resposta = await client.get(CHAMADO_URL)
                self.assertEqual(resposta.status_code, 502)
                self.assertIn(str(status), resposta.json()["detail"])
                self.assertNotIn("conteúdo interno", resposta.text)

    async def test_rejeita_404_odata_com_outro_codigo(self):
        async with api_client(lambda _: httpx.Response(404, json={"error": {"code": "OUTRO"}})) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)

    async def test_retorna_502_quando_conexao_falha(self):
        def sap(request):
            raise httpx.ConnectError("endereço interno", request=request)

        async with api_client(sap) as client:
            resposta = await client.get(CHAMADO_URL)
        self.assertEqual(resposta.status_code, 502)
        self.assertNotIn("endereço interno", resposta.text)

    async def test_retorna_504_quando_sap_expira(self):
        def sap(request):
            raise httpx.ReadTimeout("timeout", request=request)

        async with api_client(sap) as client:
            self.assertEqual((await client.get(CHAMADO_URL)).status_code, 504)

    async def test_aplica_prazo_total_da_requisicao(self):
        async def sap(_):
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={"d": ROW})

        async with api_client(sap, timeout=0.01) as client:
            self.assertEqual((await client.get(CHAMADO_URL)).status_code, 504)

    async def test_valida_numero_antes_de_consultar_sap(self):
        def sap(_):
            self.fail("O SAP não deve receber um número inválido")

        async with api_client(sap) as client:
            for numero in ("", "invalido", "12345678901", "123'", "１２３"):
                with self.subTest(numero=numero):
                    resposta = await client.get("/api/v1/chamados", params={"numero": numero})
                    self.assertEqual(resposta.status_code, 422)
            self.assertEqual((await client.get("/api/v1/chamados")).status_code, 422)

    async def test_exige_token_quando_configurado(self):
        requisicoes = []

        def sap(request):
            requisicoes.append(request)
            return httpx.Response(200, json={"d": ROW})

        async with api_client(sap, api_token="token-teste") as client:
            for headers in ({}, {"Authorization": "Bearer incorreto"}):
                self.assertEqual((await client.get(CHAMADO_URL, headers=headers)).status_code, 401)
            self.assertEqual(len(requisicoes), 0)
            com_token = await client.get(CHAMADO_URL, headers={"Authorization": "Bearer token-teste"})
        self.assertEqual(com_token.status_code, 200)
        self.assertEqual(len(requisicoes), 1)

    async def test_mandante_opcional(self):
        def sap(request):
            self.assertNotIn("sap-client", request.url.params)
            return httpx.Response(200, json={"d": ROW})

        async with api_client(sap, sap_client=None) as client:
            self.assertEqual((await client.get(CHAMADO_URL)).status_code, 200)

    async def test_health_nao_consulta_sap(self):
        def sap(_):
            self.fail("Health não deve consultar o SAP")

        async with api_client(sap, api_token="token-teste") as client:
            resposta = await client.get("/health")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})


class TestConfiguracao(TestCase):
    def test_servico_e_colecao_sao_lidos_do_env(self):
        with TemporaryDirectory() as pasta, patch.dict(os.environ, {}, clear=True):
            arquivo = Path(pasta) / ".env"
            arquivo.write_text(
                "SAP_SERVICE_URL=https://outro-sap.example/sap/opu/odata/SAP/SERVICO_FUTURO\n"
                "SAP_CHAMADOS_ENTITY_SET=ColecaoFutura\n", encoding="utf-8",
            )
            settings = Settings(_env_file=arquivo)
        self.assertEqual(settings.sap_service_url.path, "/sap/opu/odata/SAP/SERVICO_FUTURO")
        self.assertEqual(settings.sap_chamados_entity_set, "ColecaoFutura")

    def test_colecao_obrigatoria_sem_nome_padrao(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError) as contexto:
                Settings(_env_file=None, sap_service_url=SERVICE_URL)
        self.assertIn("sap_chamados_entity_set", str(contexto.exception))

    def test_rejeita_caminho_ou_query_no_nome_da_colecao(self):
        for nome in ("", "Colecao/Detalhes", "Colecao?$filter=x", "../Colecao"):
            with self.subTest(nome=nome), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, sap_service_url=SERVICE_URL, sap_chamados_entity_set=nome)

    def test_url_deve_ser_raiz_do_servico(self):
        for sufixo in (f"/{ENTITY_SET}", f"/{ENTITY_SET}('0000000123')", "/$metadata", "?$filter=x"):
            with self.subTest(sufixo=sufixo), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, sap_service_url=SERVICE_URL + sufixo, sap_chamados_entity_set=ENTITY_SET)
