import re

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

from ..core.config import MAX_PARADAS_POR_BLOCO

class OrderItem(BaseModel):
    address: str = Field(..., min_length=3, max_length=180, description="Endereço de entrega")
    amount: int = Field(..., ge=1, description="Quantidade de feijoadas")
    complement: str = Field(default="", max_length=200, description="Complemento ou Ponto de Ref.")

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str) -> str:
        value = value.strip()
        if re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("Endereço contém caracteres inválidos.")
        if re.search(r"[<>]", value):
            raise ValueError("Endereço não pode conter HTML.")
        return re.sub(r"\s+", " ", value)

class RouteRequest(BaseModel):
    orders: list[OrderItem] = Field(..., min_length=1, max_length=MAX_PARADAS_POR_BLOCO)
    optimize_for: Literal["distance", "duration"] = Field(default="distance", description="distance ou duration")
    return_to_origin: bool = Field(default=True, description="Volta ao restaurante?")

class RouteNode(BaseModel):
    address: str
    amount: int
    complement: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    weak: bool = False
    not_found: bool = False

class RouteSummary(BaseModel):
    total_stops: int
    total_amount: int

class RouteResult(BaseModel):
    distance_km: float
    route: list[RouteNode]

class GeoError(BaseModel):
    index: int
    address: str
    message: str

class RouteResponse(BaseModel):
    summary: RouteSummary
    original: RouteResult
    optimized: RouteResult
    errors: list[GeoError] = Field(default_factory=list)

class SyncRequest(BaseModel):
    origin: str = "R. Brasílio Martinho Vale, 46, Aracaju"
    stops: list[str] = Field(default_factory=list, max_length=MAX_PARADAS_POR_BLOCO)
    return_to_origin: bool = True

class SyncResponse(BaseModel):
    distance_km: Optional[float]
    source: str = "Google Maps"
