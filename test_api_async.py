import requests
import json
import time

URL = "http://127.0.0.1:8002/api/optimize_route_stream"

orders = [
    {"address": "Rod. dos Náufragos, 1900, Aruana, Aracaju - SE, 49008-093", "amount": 1},
    {"address": "Av. Poe. Vinícius de Moraes, 1171, Atalaia, Aracaju - SE, 49037-490", "amount": 1},
    {"address": "Av. Sen. Júlio César Leite, 1045, Aeroporto, Aracaju - SE, 49037-696", "amount": 1},
    {"address": "Av. D, 2-46 - Santa Maria, Aracaju, 49044-569", "amount": 1},
    {"address": "Av. Alexandre Alcino, 2980, Santa Maria, Aracaju - SE, 49044-093", "amount": 1}
]

def test_stream():
    print("Enviando requisição de otimização...")
    start_time = time.time()
    
    try:
        response = requests.post(URL, json={"orders": orders, "return_to_origin": True, "optimize_for": "distance"}, stream=True)
        
        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode('utf-8'))
                step = data.get("step")
                
                if step == "geocoding":
                    print(f"[{data['current']}/{data['total']}] Geocodificando: {data['address'][:40]}...")
                elif step == "optimizing":
                    print("--- Otimizando Rota ---")
                elif step == "done":
                    end_time = time.time()
                    print(f"\nSucesso! Tempo total: {end_time - start_time:.2f}s")
                    
                    route = data['data']['optimized']['route']
                    print("\nOrdem da Rota:")
                    for i, stop in enumerate(route):
                        status = "✅" if not stop.get('not_found') else "❌"
                        print(f"{i+1}. {status} {stop['address']}")
                    
                    dist = data['data']['optimized']['distance_km']
                    print(f"\nDistância Total: {dist} km")
    except Exception as e:
        print(f"Erro ao conectar no servidor: {e}")

if __name__ == "__main__":
    test_stream()
