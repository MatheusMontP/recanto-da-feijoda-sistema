from pydantic import BaseModel, Field
from typing import List, Optional

MAX_PARADAS_POR_BLOCO = 15

class OrderItem(BaseModel):
    address: str = Field(..., min_length=3, description="Endereço de entrega")
    amount: int = Field(..., ge=1, description="Quantidade de feijoadas")
    complement: str = Field(default="", description="Complemento ou Ponto de Ref.")

class RouteRequest(BaseModel):
    orders: List[OrderItem] = Field(..., min_length=1, max_length=MAX_PARADAS_POR_BLOCO)
    optimize_for: str = Field(default="distance", description="distance ou duration")
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
    route: List[RouteNode]

class GeoError(BaseModel):
    index: int
    address: str
    message: str

class RouteResponse(BaseModel):
    summary: RouteSummary
    original: RouteResult
    optimized: RouteResult
    errors: List[GeoError] = []

class SyncRequest(BaseModel):
    origin: str = "R. Brasílio Martinho Vale, 46, Aracaju"
    stops: List[str]
    return_to_origin: bool = True

class SyncResponse(BaseModel):
    distance_km: Optional[float]
    source: str = "Google Maps"
