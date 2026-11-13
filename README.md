# API SolMan

API de leitura para consultar um chamado por número. O FastAPI faz chamadas `GET` HTTP ou HTTPS diretamente ao serviço OData configurado em `SAP_SERVICE_URL`. Execute a API em uma máquina conectada à VPN corporativa ou em um servidor com acesso à mesma rede interna.

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
| `SAP_SERVICE_URL` | URL HTTPS da raiz do serviço informada pela equipe SAP, sem o nome da coleção nem parâmetros. O endereço em `.env.example` é fictício. |
| `SAP_CLIENT` | Mandante de três dígitos confirmado pelo Basis. Vazio usa o mandante padrão do serviço. |
| `SAP_USERNAME` e `SAP_PASSWORD` | Usuário e senha da conta técnica de leitura, se o serviço aceitar HTTP Basic. Preencha os dois. Coloque aspas simples ao redor da senha se contiver espaços ou `#`. |
| `SAP_BEARER_TOKEN` | Token aceito pelo próprio serviço SAP, se esse for o método confirmado. Deixe usuário e senha vazios nesse caso. |
| `SAP_CA_FILE` | Caminho opcional para o certificado CA corporativo em PEM, se necessário para HTTPS. |
| `SAP_TIMEOUT_SECONDS` | Tempo máximo da consulta ao SAP, em segundos. O padrão é `15`. |
| `SAP_CHAMADOS_ENTITY_SET` | Coleção para consulta por número. O exemplo usa `ChamadoSet`. |
| `SAP_DETAILS_ENTITY_SET` | Coleção para consulta dos detalhes. O exemplo usa `DetalheChamadoSet`. |
| `API_TOKEN` | Token opcional que o servidor do front-end envia à API no cabeçalho `Authorization: Bearer`. É independente da credencial do SAP. Deixe vazio para um teste local. |

Use a URL e o método de autenticação liberados para a conta técnica no DEV. Depois de registrar um novo serviço, valide a chamada com a mesma conta que a API utiliza.

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

Use `GET /api/v1/chamados?numero=0000000123`. Envie `numero` como texto com 1 a 10 dígitos para preservar zeros à esquerda. A API consulta o SAP pelo `ObjectId` e devolve `{ "chamados": [...] }`, com um item por `guid`. Se houver mais de um resultado, mostre os chamados para seleção e use `guid` como chave da lista. As datas são retornadas em ISO 8601 UTC quando preenchidas.

### Campos da tela

Os identificadores deste guia são fictícios. Para testar, use um chamado do mesmo ambiente e mandante da API.

| Campo na tela | Campo no JSON | O que já pode ser usado |
|---|---|---|
| **ID** | `chamados[].numero` | Retornado como texto. Use `guid` como identificador interno do item. |
| **Consultor Funcional Responsável** | `chamados[].parceiros[]` | A lista traz `funcao`, `descricao`, `numero_bp` e `nome`. Confirme o código `funcao` no SAP com um chamado preenchido e filtre por esse código. |
| **Desenvolvedor** | `chamados[].parceiros[]` | Use o código da função de desenvolvedor após validá-lo no SAP. |
| **Status** | `chamados[].status[]` | A API retorna os status ativos com `codigo` e `descricao`. Para exibir um único rótulo como **Novo**, confirme a regra de status principal do SolMan para o `tipo_processo`. Enquanto isso, exiba os status como lista. |
| **Nº Externo** | `chamados[].referencias_externas[].numero` | A API prevê `tipo`, `descricao` e `numero`. Valide o `tipo` correspondente ao campo da tela em um chamado preenchido. Se o valor aparecer no WebClient e estiver ausente da lista, identifique a origem técnica com **F2** para ajustar a leitura ABAP. |
| **Log de texto** | `chamados[].textos[]` | Confirmado. Cada bloco tem `tipo`, `idioma` e `linhas[]`, com `formato` e `texto`. O contrato atual entrega o conteúdo das linhas. Para exibir autor, data e hora como campos separados por entrada, é preciso incluí-los no retorno SAP e na API. |

Para listas de detalhes, `null` indica que a consulta de detalhes está sem configuração e `[]` indica que o SAP retornou zero itens para aquela lista.

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

export function nomesPorFuncao(parceiros, codigo) {
  if (parceiros == null || !codigo) return null

  return parceiros
    .filter(({ funcao }) => funcao === codigo)
    .map(({ nome }) => nome.trim())
    .filter(Boolean)
}

export function textoDoLog(bloco) {
  return bloco.linhas.map(({ texto }) => texto).join('\n')
}
```

- **Status.** Use `chamado.status.map(({ descricao, codigo }) => descricao ?? codigo)` para montar os rótulos.
- **Parceiros.** Quando os códigos estiverem confirmados, chame `nomesPorFuncao(chamado.parceiros, codigo)` uma vez para cada papel. Exiba os nomes encontrados. Mostre **Sem atribuição** quando a lista de nomes estiver vazia e reserve **Indisponível** para detalhes sem configuração ou papéis ainda sem mapeamento.
- **Nº Externo.** Exiba `numero` da referência que tiver o `tipo` confirmado. Use **Sem referência externa** para `[]` e **Indisponível** para `null`.
- **Log de texto.** Preserve a ordem dos blocos e das linhas recebidas. Use `textoDoLog` e renderize como texto com `white-space: pre-wrap` para preservar espaços e quebras de linha. Os códigos `tipo` e `idioma` podem aparecer como rótulos até que suas descrições sejam mapeadas.

| Resposta | Estado da tela |
|---|---|
| `200` com resultados | Mostre o chamado ou permita escolher quando houver mais de um. |
| `200` com `chamados: []` | Mostre **Chamado não encontrado neste ambiente**. |
| `401` | Token da API ausente ou inválido. Verifique a autenticação no servidor que encaminha a chamada. |
| `422` | Oriente o usuário a conferir o número informado. |
| `502`, `504` ou erro de rede | Mostre **Não foi possível consultar o SAP agora**. Permita uma nova tentativa. |

## Criar o serviço independente no SAP DEV

1. Na `SEGW` do backend DEV que tem os dados do CRM/SolMan, crie um projeto com tipo **Service with SAP Annotations** e geração **Standard/Default**. Os passos usam `ZCHAMADOS_DEMO` como nome de exemplo. Use o pacote indicado para os objetos Z do projeto.
2. Em **Data Model → Import → DDIC Structure**, importe `CRMD_ORDERADM_H` como entidade `Chamado`, selecionando apenas os oito campos abaixo. Confirme os nomes OData e tipos na tabela de propriedades. Crie em **Entity Sets** a coleção `ChamadoSet` para `Chamado`. Marque `Guid` como chave e `ObjectId` como filtrável.

   | Propriedade OData | Campo ABAP | Tipo OData |
   |---|---|---|
   | `Guid` | `GUID` | `Edm.Guid` |
   | `ObjectId` | `OBJECT_ID` | `Edm.String` |
   | `Description` | `DESCRIPTION` | `Edm.String` |
   | `ProcessType` | `PROCESS_TYPE` | `Edm.String` |
   | `CreatedAt` | `CREATED_AT` | `Edm.Decimal` no DEV |
   | `CreatedBy` | `CREATED_BY` | `Edm.String` |
   | `ChangedAt` | `CHANGED_AT` | `Edm.Decimal` no DEV |
   | `ChangedBy` | `CHANGED_BY` | `Edm.String` |

3. Crie a entidade `DetalheChamado` e a coleção `DetalheChamadoSet`. Adicione `Guid` como chave `Edm.Guid` e campo ABAP `GUID` do tipo `CRMT_OBJECT_GUID` (`RAW16`). Adicione `DadosJson` como `Edm.String`, campo ABAP `DADOS_JSON` do tipo `STRING`. Se preferir importar os tipos, crie uma estrutura Z no `SE11` com esses dois componentes e importe-a na `SEGW`.
4. Salve, execute **Generate Runtime Objects** e anote o nome técnico gerado. No exemplo, ele é `ZCHAMADOS_DEMO_SRV`. Em **Service Implementation**, redefina os métodos correspondentes na `DPC_EXT`. Cole cada corpo entre `METHOD` e `ENDMETHOD` e faça a verificação de sintaxe.

   | Coleção | Operação | Código ABAP |
   |---|---|---|
   | `ChamadoSet` | `GetEntitySet (Query)` | [Consulta por número](sap/chamados_get_entityset.abap) |
   | `DetalheChamadoSet` | `GetEntity (Read)` | [Leitura dos detalhes](sap/detalhes_chamado_get_entity.abap) |

5. No Gateway DEV, abra `/IWFND/MAINT_SERVICE`, escolha **Add Service** e **Get Services** usando o alias que aponta para o backend onde o projeto foi criado. Adicione o serviço gerado, confira o nó ICF e confirme que a conta técnica tem acesso ao serviço.
6. No `/IWFND/GW_CLIENT`, use os exemplos abaixo para testar as três chamadas `GET`. Troque o nome do serviço e o número pelos valores do seu ambiente. O `$metadata` deve listar as duas coleções. A segunda URI retorna os cabeçalhos do ID. Use o `Guid` da resposta na terceira URI, que devolve os detalhes em `d.DadosJson`.

   ```text
   /sap/opu/odata/SAP/ZCHAMADOS_DEMO_SRV/$metadata
   /sap/opu/odata/SAP/ZCHAMADOS_DEMO_SRV/ChamadoSet?$filter=ObjectId%20eq%20'0000000123'&$format=json
   /sap/opu/odata/SAP/ZCHAMADOS_DEMO_SRV/DetalheChamadoSet(guid'12345678-1234-4ABC-8DEF-123456789ABC')?$format=json
   ```

7. Após testar, aponte `SAP_SERVICE_URL` para a raiz do serviço registrado e use `SAP_CHAMADOS_ENTITY_SET=ChamadoSet` e `SAP_DETAILS_ENTITY_SET=DetalheChamadoSet` no `.env`. Reinicie a API e consulte o número pelo Swagger. Para conferir os campos da tela, use um chamado com consultor, desenvolvedor, número externo e log preenchidos. Se o **Nº Externo** da tela estiver ausente em `d.DadosJson`, use **F2** no WebClient para identificar a origem técnica. Confirme quais tipos de texto podem ser exibidos ao público do app antes de liberar o acesso fora do teste local.

## Testes com respostas simuladas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
