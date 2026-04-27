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
def optimize_route_endpoint(req: RouteRequest):
    """Recebe pedidos, consolida duplicatas, geocodifica e otimiza a rota."""
    origin = RESTAURANTE_COORDS

    # 1. Consolidar pedidos com mesmo endereço
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

    unique_orders = sorted(consolidated.values(), key=lambda x: x["original_idx"])

    # 2. Geocodificar
    nodes_found: list[dict] = []
    nodes_not_found: list[dict] = []
    geo_errors: list[dict] = []
    total_amount = 0

    for entry in unique_orders:
        total_amount += entry["amount"]
        res = geocode_address(entry["address"])
        
        if not res:
            msg = "Não encontrado no mapa."
            nodes_not_found.append({
                "address": entry["address"],
                "amount": entry["amount"],
                "complement": entry["complement"],
                "not_found": True
            })
            geo_errors.append({
                "index": entry["original_idx"],
                "address": entry["address"],
                "message": msg,
            })
            continue

        coords = (res["lat"], res["lon"])
        dist_from_origin = haversine(origin[0], origin[1], coords[0], coords[1])
        if dist_from_origin > 30.0:
            msg = f"Fora do raio de 30km ({dist_from_origin:.1f}km)."
            nodes_not_found.append({
                "address": entry["address"],
                "amount": entry["amount"],
                "complement": entry["complement"],
                "not_found": True
            })
            geo_errors.append({
                "index": entry["original_idx"],
                "address": entry["address"],
                "message": msg,
            })
            continue

        nodes_found.append({
            "address": entry["address"],
            "amount": entry["amount"],
            "complement": entry["complement"],
            "lat": res["lat"],
            "lon": res["lon"],
            "weak": res.get("weak", False),
            "not_found": False
        })

    all_original_nodes = nodes_found + nodes_not_found
    if not nodes_found and not nodes_not_found:
        raise HTTPException(status_code=400, detail="Nenhum endereço fornecido.")

    # 3. Matrizes e Otimização (apenas para os encontrados)
        # Log de debug para ver se as coordenadas estão batendo
        logger.info("--- [DEBUG] COORDENADAS PARA OTIMIZAÇÃO (Standard) ---")
        for i, n in enumerate(nodes_found):
            logger.info(f"Ponto {i+1}: {n['address']} -> ({n['lat']}, {n['lon']})")
        logger.info("-----------------------------------------------------")

        optimized_indices = optimize_route_exact(cost_matrix, len(nodes_found), req.return_to_origin)
        optimized_dist = compute_route_distance(dist_matrix, optimized_indices, req.return_to_origin)
        
        optimized_nodes = [nodes_found[idx - 1] for idx in optimized_indices]
        
        # Original indices based on FOUND nodes
        original_indices = list(range(1, len(nodes_found) + 1))
        original_dist = compute_route_distance(dist_matrix, original_indices, req.return_to_origin)
    else:
        optimized_nodes = []
        original_dist = 0.0
        optimized_dist = 0.0

    # Adiciona os não encontrados ao final das duas listas
    final_original = nodes_found + nodes_not_found
    final_optimized = optimized_nodes + nodes_not_found

    return RouteResponse(
        summary=RouteSummary(total_stops=len(nodes_found) + len(nodes_not_found), total_amount=total_amount),
        original=RouteResult(distance_km=round(original_dist, 2), route=final_original),
        optimized=RouteResult(distance_km=round(optimized_dist, 2), route=final_optimized),
        errors=[GeoError(**e) for e in geo_errors],
    )

@router.post("/optimize_route_stream")
async def optimize_route_stream(req: RouteRequest):
    """Versão em stream da otimização para mostrar progresso em tempo real."""
    async def generate():
        origin = RESTAURANTE_COORDS
        
        # 1. Consolidação (Rápida)
        yield json.dumps({"step": "consolidating", "message": "Organizando endereços..."}) + "\n"
        
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
        unique_orders = sorted(consolidated.values(), key=lambda x: x["original_idx"])
        total_to_geocode = len(unique_orders)

        # 2. Geocodificação (Lenta)
        nodes_found: list[dict] = []
        nodes_not_found: list[dict] = []
        geo_errors: list[dict] = []
        total_amount = 0

        for i, entry in enumerate(unique_orders):
            total_amount += entry["amount"]
            
            # Envia progresso para o frontend
            yield json.dumps({
                "step": "geocoding", 
                "current": i + 1, 
                "total": total_to_geocode, 
                "address": entry["address"]
            }) + "\n"
            
            # Executa em thread para não bloquear o loop de evento
            res = await asyncio.to_thread(geocode_address, entry["address"])
            
            # Tratar erro de imprecisão de mapa
            if res and isinstance(res, dict) and res.get("error") == "imprecise":
                 msg = "Mapa impreciso: Confirmar no Google Maps."
                 nodes_not_found.append({
                    "address": entry["address"], "amount": entry["amount"],
                    "complement": entry["complement"], "not_found": True
                })
                 geo_errors.append({
                    "index": entry["original_idx"], "address": entry["address"], "message": msg
                })
                 continue

            if not res:
                nodes_not_found.append({
                    "address": entry["address"], "amount": entry["amount"],
                    "complement": entry["complement"], "not_found": True
                })
                geo_errors.append({
                    "index": entry["original_idx"], "address": entry["address"], "message": "Não localizado."
                })
                continue

            coords = (res["lat"], res["lon"])
            dist_from_origin = haversine(origin[0], origin[1], coords[0], coords[1])
            if dist_from_origin > 45.0: # Aumentado para 45km para cobrir grande Aracaju
                nodes_not_found.append({
                    "address": entry["address"], "amount": entry["amount"],
                    "complement": entry["complement"], "not_found": True
                })
                geo_errors.append({
                    "index": entry["original_idx"], "address": entry["address"], "message": "Muito longe."
                })
                continue

            nodes_found.append({
                "address": entry["address"], "amount": entry["amount"], "complement": entry["complement"],
                "lat": res["lat"], "lon": res["lon"], "weak": res.get("weak", False), "not_found": False
            })

        # 3. Otimização
        yield json.dumps({"step": "optimizing", "message": "Calculando melhor caminho..."}) + "\n"
        
        if nodes_found:
            dur_matrix, dist_matrix = build_distance_matrix(origin, nodes_found)
            cost_matrix = dist_matrix if req.optimize_for == "distance" else dur_matrix
            
            # Log de debug para ver se as coordenadas estão batendo
            logger.info("--- [DEBUG] COORDENADAS PARA OTIMIZAÇÃO (Stream) ---")
            for i, n in enumerate(nodes_found):
                logger.info(f"Ponto {i+1}: {n['address']} -> ({n['lat']}, {n['lon']})")
            logger.info("--------------------------------------------------")

            optimized_indices = optimize_route_exact(cost_matrix, len(nodes_found), req.return_to_origin)
            optimized_dist = compute_route_distance(dist_matrix, optimized_indices, req.return_to_origin)
            optimized_nodes = [nodes_found[idx - 1] for idx in optimized_indices]
            
            original_indices = list(range(1, len(nodes_found) + 1))
            original_dist = compute_route_distance(dist_matrix, original_indices, req.return_to_origin)
        else:
            optimized_nodes = []
            original_dist = 0.0
            optimized_dist = 0.0

        final_original = nodes_found + nodes_not_found
        final_optimized = optimized_nodes + nodes_not_found

        # 4. Resultado Final
        result = RouteResponse(
            summary=RouteSummary(total_stops=len(nodes_found) + len(nodes_not_found), total_amount=total_amount),
            original=RouteResult(distance_km=round(original_dist, 2), route=final_original),
            optimized=RouteResult(distance_km=round(optimized_dist, 2), route=final_optimized),
            errors=[GeoError(**e) for e in geo_errors],
        )
        
        yield json.dumps({"step": "done", "data": result.dict()}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

@router.post("/sync_google_distance", response_model=SyncResponse)
async def sync_google_distance_endpoint(req: SyncRequest):
    """Sincroniza a quilometragem com o dado real do Google Maps via scraping."""
    dest = req.origin if req.return_to_origin else None
    dist = await get_google_maps_distance_async(req.origin, req.stops, dest)
    
    if dist is None:
        raise HTTPException(status_code=500, detail="Não foi possível obter dados do Google Maps.")
        
    return SyncResponse(distance_km=round(dist, 2))
