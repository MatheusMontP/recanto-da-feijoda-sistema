import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.geocoder import geocode_address

def test_geocoding():
    addresses = [
        "R. Brasílio Martinho Vale, 46 - Farolândia, Aracaju - SE",
        "Rua Maria Vasconcelos de Andrade, 500, Aruana, Aracaju",
        "Avenida Inácio Barbosa, 11000, Mosqueiro, Aracaju",
        "Avenida Murilo Dantas, 800, Farolândia, Aracaju"
    ]
    for addr in addresses:
        res = geocode_address(addr)
        if res:
            print(f"Address: {addr}")
            print(f"  Coords: ({res['lat']}, {res['lon']})")
            print(f"  Display: {res['display_name']}")
            print(f"  Type: {res['type']} | Importance: {res['importance']}")
        else:
            print(f"FAILED: {addr}")

if __name__ == "__main__":
    test_geocoding()
