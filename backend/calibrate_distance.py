import sys
import os
import json

# Add backend/app to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.geocoder import geocode_address
from app.services.router_engine import build_distance_matrix, compute_route_distance
from app.core.config import RESTAURANTE_COORDS

addresses = [
    "Avenida Delmiro Gouveia, 400 - Coroa do Meio",
    "Rua José Araújo Neto, 500 - São Conrado",
    "Avenida Coelho e Campos, 1254 - Centro",
    "Avenida Poço do Mero, 285 - Bugio"
]

nodes = []
for addr in addresses:
    res = geocode_address(addr)
    if res:
        nodes.append({"lat": res["lat"], "lon": res["lon"]})

print(f"Nodes found: {len(nodes)}")

dur_matrix, dist_matrix = build_distance_matrix(RESTAURANTE_COORDS, nodes)
route_indices = list(range(1, len(nodes) + 1))
raw_distance = compute_route_distance(dist_matrix, route_indices, return_to_origin=True)

print(f"OSRM Raw Distance: {raw_distance:.2f} km")
print(f"Current Calibrated (x0.93): {raw_distance * 0.93:.2f} km")
print(f"Google Maps Target: 42.4 km")
print(f"Required Multiplier: {42.4 / raw_distance:.4f}")
