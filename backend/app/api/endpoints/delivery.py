import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import json
import asyncio
from ...models.schemas import RouteRequest, RouteResponse, RouteSummary, RouteResult, GeoError, SyncRequest, SyncResponse
from ...core.config import RESTAURANTE_COORDS
from ...services.geocoder import geocode_address
from ...services.router_engine import build_distance_matrix, compute_route_distance, optimize_route_exact
from ...utils.geo import _strip_accents, haversine
from ...utils.google_maps import get_google_maps_distance_async

router = APIRouter()
logger = logging.getLogger("lucromaximo")

@router.post("/optimize_route", response_model=RouteResponse)
async def optimize_route_endpoint(req: RouteRequest):
    """Versão assíncrona do endpoint padrão."""
    origin = RESTAURANTE_COORDS

    # 1. Consolidar
    consolidated: dict[str, dict] = {}
    for idx, order in enumerate(req.orders):
        key = _strip_accents(order.address.strip().lower())
        if key in consolidated:
            consolidated[key]["amount"] += order.amount
            if order.complement:
                if consolidated[key]["complement"]:
                    if order.complement.lower() not in consolidated[key]["complement"].lower():
                        consolidated[key]["complement"] += f" | {order.complement}"
                else:
                    consolidated[key]["complement"] = order.complement
        else:
            consolidated[key] = {
                "original_idx": idx,
                "address": order.address.strip(),
                "amount": order.amount,
                "complement": order.complement.strip() if order.complement else "",
            }

    unique_orders = list(consolidated.values())
    total_amount = sum(o["amount"] for o in unique_orders)

    # 2. Geocodificar em Paralelo (O Geocoder controla a taxa internamente)
    tasks = [geocode_address(o["address"]) for o in unique_orders]
    results = await asyncio.gather(*tasks)

    nodes_found = []
    nodes_not_found = []
    geo_errors = []

    for entry, res in zip(unique_orders, results):
        if not res:
            nodes_not_found.append({"address": entry["address"], "amount": entry["amount"], "complement": entry["complement"], "not_found": True})
            geo_errors.append({"index": entry["original_idx"], "address": entry["address"], "message": "Não encontrado."})
            continue

        nodes_found.append({
            "address": entry["address"], "amount": entry["amount"], "complement": entry["complement"],
            "lat": res["lat"], "lon": res["lon"], "weak": res.get("weak", False), "not_found": False
        })

    # 3. Otimizar
    if nodes_found:
        dur_matrix, dist_matrix = build_distance_matrix(origin, nodes_found)
        cost_matrix = dist_matrix if req.optimize_for == "distance" else dur_matrix
        optimized_indices = optimize_route_exact(cost_matrix, len(nodes_found), req.return_to_origin)
        optimized_dist = compute_route_distance(dist_matrix, optimized_indices, req.return_to_origin)
        optimized_nodes = [nodes_found[idx - 1] for idx in optimized_indices]
        original_indices = list(range(1, len(nodes_found) + 1))
        original_dist = compute_route_distance(dist_matrix, original_indices, req.return_to_origin)
    else:
        optimized_nodes = []
        original_dist = optimized_dist = 0.0

    return RouteResponse(
        summary=RouteSummary(total_stops=len(unique_orders), total_amount=total_amount),
        original=RouteResult(distance_km=round(original_dist, 2), route=nodes_found + nodes_not_found),
        optimized=RouteResult(distance_km=round(optimized_dist, 2), route=optimized_nodes + nodes_not_found),
        errors=[GeoError(**e) for e in geo_errors],
    )

@router.post("/optimize_route_stream")
async def optimize_route_stream(req: RouteRequest):
    """Stream com progresso real e geocodificação paralela inteligente."""
    async def generate():
        origin = RESTAURANTE_COORDS
        yield json.dumps({"step": "consolidating", "message": "Organizando endereços..."}) + "\n"
        
        # Consolidação
        consolidated = {}
        for idx, order in enumerate(req.orders):
            key = _strip_accents(order.address.strip().lower())
            if key in consolidated:
                consolidated[key]["amount"] += order.amount
            else:
                consolidated[key] = {"idx": idx, "address": order.address.strip(), "amount": order.amount, "complement": order.complement or ""}
        
        unique_orders = sorted(consolidated.values(), key=lambda x: x["idx"])
        total_to_geocode = len(unique_orders)
        total_amount = sum(o["amount"] for o in unique_orders)

        # Geocodificação com Feedback de Progresso
        nodes_found = []
        nodes_not_found = []
        geo_errors = []
        
        # Criamos as tasks mas executamos uma a uma para o stream poder enviar o progresso
        # O benefício do 'async' aqui é que o servidor não trava e o cache é instantâneo.
        for i, entry in enumerate(unique_orders):
            yield json.dumps({
                "step": "geocoding", "current": i + 1, "total": total_to_geocode, "address": entry["address"]
            }) + "\n"
            
            res = await geocode_address(entry["address"])
            
            if not res:
                nodes_not_found.append({"address": entry["address"], "amount": entry["amount"], "complement": entry["complement"], "not_found": True})
                geo_errors.append({"index": entry["idx"], "address": entry["address"], "message": "Não localizado."})
            else:
                nodes_found.append({
                    "address": entry["address"], "amount": entry["amount"], "complement": entry["complement"],
                    "lat": res["lat"], "lon": res["lon"], "weak": res.get("weak", False), "not_found": False
                })

        # Otimização
        yield json.dumps({"step": "optimizing", "message": "Calculando melhor caminho..."}) + "\n"
        if nodes_found:
            _, dist_matrix = await build_distance_matrix(origin, nodes_found)
            optimized_indices = optimize_route_exact(dist_matrix, len(nodes_found), req.return_to_origin)
            optimized_dist = compute_route_distance(dist_matrix, optimized_indices, req.return_to_origin)
            optimized_nodes = [nodes_found[idx - 1] for idx in optimized_indices]
            original_indices = list(range(1, len(nodes_found) + 1))
            original_dist = compute_route_distance(dist_matrix, original_indices, req.return_to_origin)
        else:
            optimized_nodes = []
            original_dist = optimized_dist = 0.0

        result = RouteResponse(
            summary=RouteSummary(total_stops=len(unique_orders), total_amount=total_amount),
            original=RouteResult(distance_km=round(original_dist, 2), route=nodes_found + nodes_not_found),
            optimized=RouteResult(distance_km=round(optimized_dist, 2), route=optimized_nodes + nodes_not_found),
            errors=[GeoError(**e) for e in geo_errors],
        )
        yield json.dumps({"step": "done", "data": result.dict()}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

@router.post("/sync_google_distance", response_model=SyncResponse)
async def sync_google_distance_endpoint(req: SyncRequest):
    dest = req.origin if req.return_to_origin else None
    dist = await get_google_maps_distance_async(req.origin, req.stops, dest)
    if dist is None: raise HTTPException(status_code=500, detail="Erro no Google Maps.")
    return SyncResponse(distance_km=round(dist, 2))
