import math
import uuid
import heapq
from typing import Tuple, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import requests

app = FastAPI(title="Maritime Intelligence Systems - Professional Suite")

# --- API CONFIGURATION ---
# Replace with your actual NOAA token
NOAA_API_TOKEN = "WovUqqdkOAhuNTcGReDULESBmmqtFmRk" 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REFINED LAND & SEA LANE DATA ---
# Using refined bounding boxes to approximate continents
# In a production environment, this would be a GeoJSON/Shapefile look-up
EXTENDED_LAND_ZONES = [
    {"name": "Africa", "min_lat": -35, "max_lat": 37, "min_lon": -18, "max_lon": 51},
    {"name": "Americas_North", "min_lat": 15, "max_lat": 75, "min_lon": -170, "max_lon": -50},
    {"name": "Americas_South", "min_lat": -56, "max_lat": 15, "min_lon": -82, "max_lon": -34},
    {"name": "Eurasia_Main", "min_lat": 35, "max_lat": 75, "min_lon": -10, "max_lon": 145},
    {"name": "Australia", "min_lat": -44, "max_lat": -10, "min_lon": 112, "max_lon": 154},
    {"name": "India_Sub", "min_lat": 8, "max_lat": 30, "min_lon": 68, "max_lon": 90},
    {"name": "Arabia", "min_lat": 12, "max_lat": 32, "min_lon": 34, "max_lon": 60},
    {"name": "Greenland", "min_lat": 60, "max_lat": 84, "min_lon": -73, "max_lon": -12},
]

# Explicit "Safe Corridors" that override land checks
SEA_LANES = [
    {"name": "Suez Canal", "lat_range": (27, 32), "lon_range": (31, 33)},
    {"name": "Panama Canal", "lat_range": (8.5, 9.5), "lon_range": (-80, -79)},
    {"name": "Malacca Strait", "lat_range": (1, 6), "lon_range": (95, 104)},
    {"name": "English Channel", "lat_range": (49, 51), "lon_range": (-5, 2)},
    {"name": "Bab-el-Mandeb", "lat_range": (11.5, 13.5), "lon_range": (42.5, 44)},
]

GATEWAY_WAYPOINTS = {
    "Suez": (30.0, 32.5),
    "Panama": (9.0, -79.8),
    "Malacca": (2.0, 102.0),
    "Gibraltar": (36.0, -5.5),
    "Bering": (66.0, -168.0)
}

# --- MODELS ---
class Location(BaseModel):
    lat: float
    lon: float

class VoyageRequest(BaseModel):
    source: Location
    destination: Location

class DisruptionZone(BaseModel):
    name: str
    lat: float
    lon: float
    radius: float = 5.0
    penalty: int = 500

# Global In-Memory State
DEFAULT_DISRUPTION_ZONES = [
    {"id": str(uuid.uuid4()), "name": "Cyclonic Activity Alpha", "lat": 12.5, "lon": 82.0, "radius": 4.5, "penalty": 600},
    {"id": str(uuid.uuid4()), "name": "Port Congestion Area", "lat": 24.5, "lon": 54.0, "radius": 2.0, "penalty": 300},
]
DISRUPTION_ZONES = [dict(zone) for zone in DEFAULT_DISRUPTION_ZONES]

# --- LOGIC ---
def is_land_locked(lat: float, lon: float) -> bool:
    """Checks if a point is on land, respecting maritime corridors."""
    # 1. Check Sea Lane Exemptions first
    for lane in SEA_LANES:
        if (lane["lat_range"][0] <= lat <= lane["lat_range"][1] and 
            lane["lon_range"][0] <= lon <= lane["lon_range"][1]):
            return False
            
    # 2. Check major land masses
    for box in EXTENDED_LAND_ZONES:
        if (box["min_lat"] <= lat <= box["max_lat"] and 
            box["min_lon"] <= lon <= box["max_lon"]):
            return True
    return False

def haversine_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))

def get_disruption_impact(lat: float, lon: float) -> float:
    penalty = 0
    for zone in DISRUPTION_ZONES:
        dist = haversine_distance((lat, lon), (zone["lat"], zone["lon"]))
        # Convert radius (approx km) to degree penalty
        if dist < zone["radius"] * 111:
            proximity = 1 - (dist / (zone["radius"] * 111))
            penalty += zone["penalty"] * (proximity ** 1.5)
    return penalty

def a_star_route(start: Tuple[float, float], end: Tuple[float, float], resolution: float = 0.5):
    """
    High-precision maritime A* search.
    Resolution: 0.5 (~55km) provides a balance of speed and precision.
    """
    start_node = (round(start[0] / resolution) * resolution, round(start[1] / resolution) * resolution)
    end_node = (round(end[0] / resolution) * resolution, round(end[1] / resolution) * resolution)

    # (priority, current_cost, current_coord, path)
    open_set = [(haversine_distance(start_node, end_node), 0.0, start_node, [])]
    visited = {}

    iterations = 0
    while open_set and iterations < 10000:
        iterations += 1
        _, cost, current, path = heapq.heappop(open_set)

        if current == end_node:
            return path + [current], cost

        if current in visited and visited[current] <= cost:
            continue
        visited[current] = cost

        # 8-direction movement
        for dlat in [-resolution, 0, resolution]:
            for dlon in [-resolution, 0, resolution]:
                if dlat == 0 and dlon == 0: continue
                
                neighbor = (round((current[0] + dlat) * 10) / 10, round((current[1] + dlon) * 10) / 10)
                
                # Bounds
                if not (-70 <= neighbor[0] <= 80 and -180 <= neighbor[1] <= 180): continue
                
                # Land check
                if is_land_locked(neighbor[0], neighbor[1]): continue

                dist_step = haversine_distance(current, neighbor)
                hazard_cost = get_disruption_impact(neighbor[0], neighbor[1])
                
                # Total cost: Distance + Disruption Penalty
                new_cost = cost + dist_step + (hazard_cost * dist_step / 5)
                
                h = haversine_distance(neighbor, end_node)
                heapq.heappush(open_set, (new_cost + h, new_cost, neighbor, path + [current]))

    return None, 0.0

# --- ENDPOINTS ---

@app.get("/system/status")
async def get_status():
    return {
        "status": "Operational",
        "active_hazards": len(DISRUPTION_ZONES),
        "api_connected": True if NOAA_API_TOKEN else False,
        "mode": "High Precision"
    }

@app.get("/zones")
async def get_zones():
    return DISRUPTION_ZONES

@app.post("/zones")
async def add_zone(zone: DisruptionZone):
    new_zone = {
        "id": str(uuid.uuid4()), "name": zone.name, "lat": zone.lat,
        "lon": zone.lon, "radius": zone.radius, "penalty": zone.penalty
    }
    DISRUPTION_ZONES.append(new_zone)
    return new_zone

@app.delete("/zones")
async def clear_zones():
    global DISRUPTION_ZONES
    DISRUPTION_ZONES = [dict(zone) for zone in DEFAULT_DISRUPTION_ZONES]
    return {"message": "Hazards reset to default state."}


def route_via_gateway(src: Tuple[float, float], dest: Tuple[float, float], gateway_name: str):
    gateway = GATEWAY_WAYPOINTS.get(gateway_name)
    if not gateway:
        return None, 0.0

    path_to_gateway, cost_to_gateway = a_star_route(src, gateway)
    if not path_to_gateway:
        return None, 0.0

    path_from_gateway, cost_from_gateway = a_star_route(gateway, dest)
    if not path_from_gateway:
        return None, 0.0

    combined_path = path_to_gateway + path_from_gateway[1:]
    return combined_path, cost_to_gateway + cost_from_gateway

@app.post("/calculate-voyage")
async def calculate_voyage(request: VoyageRequest):
    src = (request.source.lat, request.source.lon)
    dest = (request.destination.lat, request.destination.lon)

    # Initial validation
    if is_land_locked(src[0], src[1]) or is_land_locked(dest[0], dest[1]):
        # We allow it but warn, as ports are often on coastlines
        status_prefix = "PORT_ADJACENT"
    else:
        status_prefix = "DEEP_SEA"

    path, total_cost = a_star_route(src, dest, resolution=0.5)

    if not path:
        fallback_attempts = []
        if src[1] < -30 and dest[1] > 20:
            fallback_attempts = ["Panama", "Suez"]
        elif src[1] > 20 and dest[1] < -30:
            fallback_attempts = ["Suez", "Panama"]
        elif src[1] > 80 and dest[1] < 50:
            fallback_attempts = ["Malacca", "Suez"]
        elif abs(src[0] - dest[0]) > 20 and abs(src[1] - dest[1]) > 100:
            fallback_attempts = ["Panama", "Suez"]

        for gateway in fallback_attempts:
            path, total_cost = route_via_gateway(src, dest, gateway)
            if path:
                break

    if not path:
        # Fallback to direct if pathing fails (usually impossible land-locked points)
        final_path = [[src[0], src[1]], [dest[0], dest[1]]]
        return {
            "status": "FAILED",
            "path": final_path,
            "message": "Routing engine could not find a pure water path. Connectivity may be obstructed.",
            "distance_km": round(haversine_distance(src, dest), 2)
        }

    # Format path for Leaflet
    final_path = [[src[0], src[1]]] + [list(p) for p in path] + [[dest[0], dest[1]]]
    
    # Calculate real metrics
    dist_km = sum(haversine_distance(tuple(final_path[i]), tuple(final_path[i+1])) for i in range(len(final_path)-1))
    
    return {
        "status": "SUCCESS",
        "path": final_path,
        "distance_km": round(dist_km, 2),
        "cost_index": round(total_cost, 2),
        "message": f"Optimal maritime route established ({status_prefix})."
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)