# API SolMan

API de leitura para consultar chamados por número. Cada consulta válida faz **um único GET** no SAP Gateway com o `ObjectId` na URI, em `ChamadoUnificadoSet('NUMERO')`. O Gateway devolve o cabeçalho e os detalhes juntos.

Execute a API em uma máquina conectada à VPN corporativa ou em um servidor com acesso à rede interna. A raiz do serviço e o nome da coleção são configuráveis no `.env`.

Este README é a referência do fluxo unificado. O guia Word existente foi preservado com suas alterações locais e pode conter instruções do fluxo anterior.

## Iniciar no Windows

Use Python 3.11 ou mais recente. Na pasta do projeto, em PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

### Variáveis do `.env`

| Variável | Valor |
|---|---|
| `SAP_SERVICE_URL` | Obrigatória. URL da raiz do serviço informada pela equipe SAP, sem coleção nem parâmetros. Prefira HTTPS. Não há endereço padrão. |
| `SAP_CLIENT` | Mandante de três dígitos confirmado pelo Basis. Vazio usa o mandante padrão do serviço. |
| `SAP_USERNAME` e `SAP_PASSWORD` | Usuário e senha da conta técnica de leitura, se o serviço aceitar HTTP Basic. Preencha os dois. Coloque aspas simples ao redor da senha se contiver espaços ou `#`. |
| `SAP_BEARER_TOKEN` | Token aceito pelo próprio serviço SAP, se esse for o método confirmado. Deixe usuário e senha vazios nesse caso. |
| `SAP_CA_FILE` | Caminho opcional para o certificado CA corporativo em PEM, se necessário para HTTPS. |
| `SAP_TIMEOUT_SECONDS` | Tempo máximo da consulta ao SAP, em segundos. O padrão é `15`. |
| `SAP_CHAMADOS_ENTITY_SET` | Obrigatória. Use `ChamadoUnificadoSet` ou o nome publicado no `$metadata` do ambiente. Informe somente o nome. |
| `API_TOKEN` | Token opcional que o servidor do front-end envia à API no cabeçalho `Authorization: Bearer`. É independente da credencial do SAP. Deixe vazio para um teste local. |

Use a URL e o método de autenticação liberados para a conta técnica no DEV. Depois de registrar um novo serviço, valide a chamada com a mesma conta que a API utiliza.

Use a raiz do serviço do ambiente e o nome da coleção para preencher as duas variáveis. Exemplo com host fictício.

```dotenv
SAP_SERVICE_URL=https://sap.example.com/sap/opu/odata/SAP/ZSOLMAN_API_SRV
SAP_CHAMADOS_ENTITY_SET=ChamadoUnificadoSet
```

Reinicie o Uvicorn após alterar o `.env`.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra o [Swagger local](http://127.0.0.1:8000/docs) ou faça a consulta em outro PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/chamados?numero=0000000123' |
    ConvertTo-Json -Depth 12
```

Se configurou `API_TOKEN`, use **Authorize** no Swagger. `GET /health` verifica que a API está rodando. A consulta de chamados verifica a integração com o SAP.

## Contrato da consulta

Use `GET /api/v1/chamados?numero=0000000123`. Envie `numero` como texto com 1 a 10 dígitos para preservar zeros à esquerda. A API consulta o SAP por `ObjectId` e devolve `{"chamados": [...]}` com um item quando o chamado existe. Para um chamado inexistente, devolve `{"chamados": []}`. As datas de criação e atualização preenchidas são retornadas em ISO 8601 UTC.

### Campos da tela

Os identificadores deste guia são fictícios. Para testar, use um chamado do mesmo ambiente e mandante da API.

| Campo na tela | Campo no JSON | Valor |
|---|---|---|
| **ID** | `chamados[].numero` | Número do chamado como texto. |
| **Consultor Funcional Responsável** | `chamados[].consultor_funcional` | Nome publicado em `ConsultorFuncional`, ou `""` quando vazio. |
| **Desenvolvedor ABAP** | `chamados[].desenvolvedor_abap` | Nome publicado em `DesenvolvedorAbap`, ou `""` quando vazio. |
| **Status** | `chamados[].status` | Texto recebido em `Status`, por exemplo `NEW (Novo)`. |
| **Nº Externo** | `chamados[].numero_externo` | Texto recebido em `ReferenciasExternas`, ou `null` quando vazio. |
| **Log de texto** | `chamados[].textos` | String de `Textos`, com as quebras de linha e os espaços do SAP. |
| **Estimativa em horas** | `chamados[].estimativa` | Decimal de `Estimativa` como string, por exemplo `"89.000"`. Retorna `null` quando ausente. |
| **Início do desenvolvimento** | `chamados[].data_inicio_desenvolvimento` | Data de `DtIniDesenv`, em `DD-MM-YYYY` no formato OData atual. |
| **Fim do desenvolvimento** | `chamados[].data_fim_desenvolvimento` | Data de `DtFimDesenv`, em `DD-MM-YYYY` no formato OData atual. |
| **Data desejada pelo cliente** | `chamados[].data_desejada_cliente` | Data de `DtDesejCliente`, em `DD-MM-YYYY` no formato OData atual. |

### Contrato esperado do OData unificado

Exemplo de URI montada pela API.

```text
{SAP_SERVICE_URL}/{SAP_CHAMADOS_ENTITY_SET}('0000000123')?$format=json
```

Quando configurado, `sap-client` é acrescentado à query. O Gateway devolve uma entidade diretamente em `d` com os campos de cabeçalho e detalhes. A API verifica se o `ObjectId` corresponde ao número solicitado e valida os campos de detalhes conforme seus tipos. `Estimativa` tem precisão 13 e escala 3. As três datas de planejamento são `Edm.DateTime` no Gateway e chegam como `/Date(...)/`. A API devolve essas datas em `DD-MM-YYYY` para exibição direta. Datas ausentes ou nulas retornam `null`. Para ambientes com o contrato anterior, o decimal zero retorna `null` e os demais decimais continuam sendo repassados como strings. [Exemplo de resposta do SAP](sap/resposta_unificada.example.json)

O `404` do Gateway com código OData `/IWBEP/CM_MGW_RT/020` indica chamado inexistente. Outros `404` do Gateway viram `502`. As datas do cabeçalho aceitam `/Date(...)/` e timestamps SAP de 14 dígitos, inclusive com fração decimal. Datas vazias ou zeradas tornam-se `null`.

## Consumir no front-end

### 1. Configurar a chamada do navegador

Use o caminho relativo `/api/v1/chamados` no front-end. A API atual não habilita CORS, então encaminhe esse caminho pelo servidor do site na mesma origem. O navegador chama o servidor do site, que chama a API SolMan. A API SolMan usa a conta técnica para falar com o SAP. [CORS e origem no navegador](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)

**Exemplo local com Vite.** Acrescente a opção `server.proxy` abaixo ao `vite.config.js` ou `vite.config.ts` do front-end. Inicie o FastAPI em `127.0.0.1:8000` e reinicie o Vite após alterar a configuração. [Proxy do Vite](https://vite.dev/config/server-options#server-proxy) · [Variáveis na configuração do Vite](https://vite.dev/config/#using-environment-variables-in-config)

```js
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'SOLMAN_')
  const token = env.SOLMAN_API_TOKEN

  return {
    server: {
      proxy: {
        '^/api/v1/chamados(?:[?]|$)': {
          target: env.SOLMAN_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      },
    },
  }
})
```

No `.env.local` do **front-end**, use `SOLMAN_API_URL=http://127.0.0.1:8000` ou o endereço acessível pelo servidor do site. Se o `.env` da API tiver `API_TOKEN`, configure o mesmo valor como `SOLMAN_API_TOKEN` no servidor do front-end. Mantenha esse token em uma variável de servidor, fora de `VITE_*`. As credenciais SAP ficam na API SolMan. [Variáveis expostas ao navegador no Vite](https://vite.dev/guide/env-and-mode)

Na publicação, configure o backend do site para encaminhar essa rota. É ali que você valida a sessão do usuário e quais chamados e tipos de texto ele pode consultar. O endereço da API deve ser acessível a partir desse servidor. O proxy do Vite acima é para desenvolvimento local.

### 2. Buscar e exibir o chamado

Use um campo de texto com `inputmode="numeric"` e passe o valor digitado a `buscarChamados` ao enviar o formulário. Mostre um estado de carregamento enquanto a consulta está pendente. Se o usuário iniciar outra busca, você pode cancelar a anterior com `AbortController`. [Tratamento de respostas com Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)

```js
export async function buscarChamados(numero, signal) {
  const id = numero.trim()
  if (!/^[0-9]{1,10}$/.test(id)) {
    throw new Error('Informe um número de chamado com 1 a 10 dígitos.')
  }

  const query = new URLSearchParams({ numero: id })
  const resposta = await fetch(`/api/v1/chamados?${query}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!resposta.ok) {
    throw Object.assign(new Error('Falha na consulta do chamado.'), {
      status: resposta.status,
    })
  }

  const dados = await resposta.json()
  if (!Array.isArray(dados?.chamados)) {
    throw new Error('Resposta da API fora do formato esperado.')
  }
  return dados.chamados
}
```

Mostre **—** nos campos vazios. Aplique essa regra na apresentação para valores `null`, ausentes ou compostos apenas de espaços. Uma estimativa `"0.000"` é um valor presente.

Quando `chamado.textos` tiver conteúdo, mostre **Ver log** com o painel fechado. Ao abrir o painel, exiba o texto completo. Para um log vazio, mostre **—**.

```js
export function valorDoCampo(valor) {
  if (valor == null || (typeof valor === 'string' && valor.trim() === '')) {
    return '—'
  }
  return valor
}

export function exibirLog(elemento, textos) {
  if (!textos?.trim()) {
    elemento.textContent = '—'
    return
  }

  const painel = document.createElement('details')
  const rotulo = document.createElement('summary')
  rotulo.textContent = 'Ver log'

  const conteudo = document.createElement('pre')
  conteudo.style.whiteSpace = 'pre-wrap'
  conteudo.textContent = textos

  painel.append(rotulo, conteudo)
  elemento.replaceChildren(painel)
}
```

`exibirLog` usa `trim()` para verificar se há conteúdo e passa `textos` integralmente para o painel, preservando as quebras de linha, as linhas vazias e os espaços.

| Resposta | Estado da tela |
|---|---|
| `200` com um item em `chamados` | Mostre o chamado. |
| `200` com `chamados: []` | Mostre **Chamado não encontrado neste ambiente**. |
| `401` | Token da API ausente ou inválido. Verifique a autenticação no servidor que encaminha a chamada. |
| `422` | Oriente o usuário a conferir o número informado. |
| `502`, `504` ou erro de rede | Mostre **Não foi possível consultar o SAP agora**. Permita uma nova tentativa. |

## Validar o serviço no SAP DEV

1. No `/IWFND/GW_CLIENT`, confira no `$metadata` que `ObjectId` é a chave. `Status`, `ConsultorFuncional`, `DesenvolvedorAbap`, `ReferenciasExternas` e `Textos` são `Edm.String`. `Estimativa` é `Edm.Decimal`, e `DtIniDesenv`, `DtFimDesenv` e `DtDesejCliente` são `Edm.DateTime`.
2. Consulte `/sap/opu/odata/SAP/ZSOLMAN_API_SRV/ChamadoUnificadoSet('0000000123')?$format=json` com um número válido no mandante da API. Compare o status, os responsáveis, o número externo e o log com o SolMan.
3. Use o Swagger da API para repetir a consulta. Valide também um chamado sem referência externa e uma chave inexistente.

Os arquivos ABAP em `sap/` são referências dos contratos anteriores. O JSON de exemplo representa o contrato publicado pelo `GET_ENTITY` atual.

## Testes com respostas simuladas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes simulam o Gateway e cobrem a consulta por chave em um GET, o mapeamento dos responsáveis, a preservação integral do log, o chamado inexistente, a validação da resposta, as datas, a configuração, a autenticação e falhas de conexão e timeout.
