import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, Field, Json, field_validator

SAP_DATE = re.compile(r"/Date\((-?[0-9]+)([+-][0-9]{4})?\)/")
SAP_TIMESTAMP = re.compile(r"([0-9]{14})(?:\.([0-9]{1,7}))?")
SAP_ZERO_TIMESTAMP = re.compile(r"0{1,14}(?:\.0{1,7})?")
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class SapChamado(BaseModel):
    guid: UUID = Field(alias="Guid")
    numero: str = Field(alias="ObjectId")
    descricao: str = Field(alias="Description")
    tipo_processo: str = Field(alias="ProcessType")
    criado_em: datetime | None = Field(default=None, alias="CreatedAt")
    criado_por: str | None = Field(default=None, alias="CreatedBy")
    atualizado_em: datetime | None = Field(default=None, alias="ChangedAt")
    atualizado_por: str | None = Field(default=None, alias="ChangedBy")
    codigo_status: str | None = Field(default=None, alias="Stat")
    descricao_status: str | None = Field(default=None, alias="Txt30")

    @field_validator("criado_em", "atualizado_em", mode="before")
    @classmethod
    def parse_sap_date(cls, value: object) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            value = str(value)
        if not isinstance(value, str):
            raise ValueError("Data fora do formato SAP esperado")
        if SAP_ZERO_TIMESTAMP.fullmatch(value):
            return None

        try:
            match = SAP_DATE.fullmatch(value)
            if match:
                milliseconds, offset = match.groups()
                return UNIX_EPOCH + timedelta(milliseconds=int(milliseconds), minutes=int(offset or 0))

            match = SAP_TIMESTAMP.fullmatch(value)
            if match:
                timestamp, fraction = match.groups()
                microsecond = int((fraction or "").ljust(6, "0")[:6])
                return datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc, microsecond=microsecond
                )
        except (ValueError, OverflowError) as error:
            raise ValueError("Data SAP inválida") from error
        raise ValueError("Data fora do formato SAP esperado")


class SapPagina(BaseModel):
    results: list[SapChamado]
    proxima: str | None = Field(default=None, alias="__next")


class SapResposta(BaseModel):
    d: SapPagina


class StatusChamado(BaseModel):
    codigo: str
    descricao: str | None

    @field_validator("descricao")
    @classmethod
    def normalizar_descricao(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class ParceiroChamado(BaseModel):
    funcao: str
    descricao: str
    numero_bp: str
    nome: str


class ReferenciaExterna(BaseModel):
    tipo: str
    descricao: str
    numero: str


class LinhaTexto(BaseModel):
    formato: str
    texto: str


class TextoChamado(BaseModel):
    tipo: str
    idioma: str
    linhas: list[LinhaTexto]


class DetalhesChamado(BaseModel):
    status: list[StatusChamado]
    parceiros: list[ParceiroChamado]
    referencias_externas: list[ReferenciaExterna]
    textos: list[TextoChamado]


class SapDetalheChamado(BaseModel):
    guid: UUID = Field(alias="Guid")
    dados: Json[DetalhesChamado] = Field(alias="DadosJson")


class SapRespostaDetalhe(BaseModel):
    d: SapDetalheChamado


class Chamado(BaseModel):
    guid: UUID
    numero: str
    descricao: str
    tipo_processo: str
    criado_em: datetime | None
    criado_por: str | None
    atualizado_em: datetime | None
    atualizado_por: str | None
    status: list[StatusChamado] = Field(default_factory=list)
    parceiros: list[ParceiroChamado] | None = None
    referencias_externas: list[ReferenciaExterna] | None = None
    textos: list[TextoChamado] | None = None


class RespostaChamados(BaseModel):
    chamados: list[Chamado]
