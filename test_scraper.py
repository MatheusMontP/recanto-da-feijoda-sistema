import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.utils.google_maps import get_google_maps_distance

def test():
    origin = "Avenida Delmiro Gouveia, 400"
    stops = [
        "Rua José Araújo Neto, 500, São Conrado, Aracaju, SE",
        "Avenida Alexandre Alcino, Aracaju"
    ]
    print(f"Testando scraper com {len(stops)} paradas...")
    distance = get_google_maps_distance(origin, stops, origin)
    print(f"Distância obtida: {distance} km")

if __name__ == "__main__":
    test()
