from contextlib import asynccontextmanager
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.sap import SapError, SapGateway, create_http_client
from app.schemas import RespostaChamados

bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    async with create_http_client(settings) as client:
        app.state.sap = SapGateway(client, settings)
        app.state.api_token = settings.api_token
        yield


app = FastAPI(title="API SolMan", version="0.1.0", lifespan=lifespan)


async def autenticar(
    request: Request,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = request.app.state.api_token
    if token is None:
        return
    if credenciais is None or not compare_digest(
        credenciais.credentials.encode(), token.get_secret_value().encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Informe o token da API SolMan.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/chamados", dependencies=[Depends(autenticar)])
async def consultar_chamados(
    request: Request,
    numero: Annotated[str, Query(pattern=r"^[0-9]{1,10}$", description="Número do chamado no SAP")],
) -> RespostaChamados:
    sap: SapGateway = request.app.state.sap
    try:
        return RespostaChamados(chamados=await sap.consultar(numero))
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="O SAP demorou a responder.") from error
    except SapError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
