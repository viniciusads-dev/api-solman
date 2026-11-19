import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator

SAP_DATE = re.compile(r"/Date\((-?[0-9]+)([+-][0-9]{4})?\)/")
SAP_TIMESTAMP = re.compile(r"([0-9]{14})(?:\.([0-9]{1,7}))?")
SAP_ZERO_TIMESTAMP = re.compile(r"0{1,14}(?:\.0{1,7})?")
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
DataPlanejadaSap = Annotated[Decimal, Field(max_digits=15, decimal_places=0)] | Annotated[
    date, Field(strict=True)
]


def parse_odata_date(match: re.Match[str]) -> datetime:
    milliseconds, offset = match.groups()
    try:
        return UNIX_EPOCH + timedelta(milliseconds=int(milliseconds), minutes=int(offset or 0))
    except (ValueError, OverflowError) as error:
        raise ValueError("Data SAP inválida") from error


class SapCabecalho(BaseModel):
    guid: UUID = Field(alias="Guid")
    numero: str = Field(alias="ObjectId")
    descricao: str = Field(alias="Description")
    tipo_processo: str = Field(alias="ProcessType")
    criado_em: datetime | None = Field(default=None, alias="CreatedAt")
    criado_por: str | None = Field(default=None, alias="CreatedBy")
    atualizado_em: datetime | None = Field(default=None, alias="ChangedAt")
    atualizado_por: str | None = Field(default=None, alias="ChangedBy")

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

        match = SAP_DATE.fullmatch(value)
        if match:
            return parse_odata_date(match)

        try:
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


class SapChamado(SapCabecalho):
    status: str = Field(alias="Status")
    consultor_funcional: str = Field(alias="ConsultorFuncional")
    desenvolvedor_abap: str = Field(alias="DesenvolvedorAbap")
    numero_externo: str = Field(alias="ReferenciasExternas")
    textos: str = Field(alias="Textos")
    estimativa: Decimal | None = Field(default=None, alias="Estimativa", max_digits=13, decimal_places=3)
    data_inicio_desenvolvimento: DataPlanejadaSap | None = Field(default=None, alias="DtIniDesenv")
    data_fim_desenvolvimento: DataPlanejadaSap | None = Field(default=None, alias="DtFimDesenv")
    data_desejada_cliente: DataPlanejadaSap | None = Field(default=None, alias="DtDesejCliente")

    @field_validator(
        "data_inicio_desenvolvimento", "data_fim_desenvolvimento", "data_desejada_cliente", mode="before"
    )
    @classmethod
    def converter_data_planejada_odata(cls, value: object) -> object:
        if isinstance(value, str):
            match = SAP_DATE.fullmatch(value)
            if match:
                return parse_odata_date(match).date()
        return value

    @field_validator("data_inicio_desenvolvimento", "data_fim_desenvolvimento", "data_desejada_cliente")
    @classmethod
    def normalizar_data_planejada(cls, value: DataPlanejadaSap | None) -> DataPlanejadaSap | None:
        return None if value == 0 else value


class SapResposta(BaseModel):
    d: SapChamado


class Chamado(BaseModel):
    guid: UUID
    numero: str
    descricao: str
    tipo_processo: str
    criado_em: datetime | None
    criado_por: str | None
    atualizado_em: datetime | None
    atualizado_por: str | None
    status: str
    consultor_funcional: str
    desenvolvedor_abap: str
    numero_externo: str | None
    textos: str
    estimativa: Decimal | None
    data_inicio_desenvolvimento: date | Decimal | None
    data_fim_desenvolvimento: date | Decimal | None
    data_desejada_cliente: date | Decimal | None

    @field_serializer(
        "data_inicio_desenvolvimento", "data_fim_desenvolvimento", "data_desejada_cliente", when_used="json"
    )
    def formatar_data_planejada(self, value: date | Decimal | None) -> str | None:
        if isinstance(value, date):
            return f"{value.day:02d}-{value.month:02d}-{value.year:04d}"
        return str(value) if value is not None else None

    @field_validator("numero_externo")
    @classmethod
    def normalizar_numero_externo(cls, value: str | None) -> str | None:
        return value or None


class RespostaChamados(BaseModel):
    chamados: list[Chamado]
