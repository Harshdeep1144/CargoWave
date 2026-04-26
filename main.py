from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
import math
import heapq
import uvicorn

app = FastAPI(title="Smart Supply Chain - Maritime Brain v3 (Dijkstra)")

# --- CORS SETUP ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION & MOCK DATA ---
DISRUPTION_ZONES = [
    {"name": "Tropical Storm Alpha", "lat": 8.0, "lon": 73.0, "radius": 5.0, "penalty": 500}, 
    {"name": "Suez Congestion", "lat": 29.9, "lon": 32.5, "radius": 2.5, "penalty": 300}
]

# Simplified Land Bounding Boxes (Approximation for the demo region)
LAND_BOXES = [
    {"name": "Africa", "min_lat": -35, "max_lat": 37, "min_lon": -20, "max_lon": 51},
    {"name": "Arabian Peninsula", "min_lat": 12, "max_lat": 30, "min_lon": 35, "max_lon": 59},
    {"name": "India", "min_lat": 8, "max_lat": 35, "min_lon": 68, "max_lon": 97},
    {"name": "Indochina/Malay", "min_lat": 1, "max_lat": 25, "min_lon": 98, "max_lon": 110}
]

class Location(BaseModel):
    lat: float
    lon: float

class VoyageRequest(BaseModel):
    source: Location
    destination: Location

# --- ROUTING UTILITIES ---

def is_on_land(lat: float, lon: float) -> bool:
    """Check if coordinates fall within simplified land boundaries."""
    # Allow safe passage through known maritime corridors despite bounding boxes
    # Suez Canal Area
    if 27 <= lat <= 32 and 31 <= lon <= 34: return False
    # Strait of Malacca
    if 1 <= lat <= 6 and 95 <= lon <= 104: return False
    # Bab-el-Mandeb
    if 11 <= lat <= 14 and 42 <= lon <= 45: return False
    
    for box in LAND_BOXES:
        if box["min_lat"] <= lat <= box["max_lat"] and box["min_lon"] <= lon <= box["max_lon"]:
            return True
    return False

def haversine_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate the great-circle distance between two points on Earth."""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return 6371 * 2 * math.asin(math.sqrt(a))

def get_disruption_cost(lat: float, lon: float) -> float:
    """Calculate additional weight penalty based on proximity to hazards."""
    penalty = 0
    for zone in DISRUPTION_ZONES:
        dist = haversine_distance((lat, lon), (zone['lat'], zone['lon']))
        # Convert radius (roughly degrees) to km (1 deg ~ 111km)
        if dist < (zone['radius'] * 111):
            penalty += zone['penalty']
    return penalty

# --- DIJKSTRA IMPLEMENTATION ---

def dijkstra_search(start: Tuple[float, float], end: Tuple[float, float], resolution: int = 2):
    """
    Finds shortest sea path using Dijkstra's algorithm.
    resolution: Grid spacing in degrees.
    """
    # Round start/end to nearest grid points
    start_node = (round(start[0] / resolution) * resolution, round(start[1] / resolution) * resolution)
    end_node = (round(end[0] / resolution) * resolution, round(end[1] / resolution) * resolution)

    queue = [(0, start_node, [])]
    visited = set()
    distances = {start_node: 0}

    while queue:
        (cost, current, path) = heapq.heappop(queue)

        if current in visited:
            continue

        visited.add(current)
        path = path + [current]

        if current == end_node:
            return path, cost

        # Check 8 neighbors
        for dlat in [-resolution, 0, resolution]:
            for dlon in [-resolution, 0, resolution]:
                if dlat == 0 and dlon == 0: continue
                
                neighbor = (current[0] + dlat, current[1] + dlon)
                
                # Global boundary constraints
                if not (-70 <= neighbor[0] <= 80 and -180 <= neighbor[1] <= 180): continue
                
                # LAND AVOIDANCE
                if is_on_land(neighbor[0], neighbor[1]): continue

                # Calculate weights: distance + environmental penalty
                step_dist = haversine_distance(current, neighbor)
                hazard_penalty = get_disruption_cost(neighbor[0], neighbor[1])
                new_cost = cost + step_dist + hazard_penalty

                if neighbor not in distances or new_cost < distances[neighbor]:
                    distances[neighbor] = new_cost
                    heapq.heappush(queue, (new_cost, neighbor, path))

    return None, 0

# --- ENDPOINTS ---

@app.get("/environment-data")
async def get_environment():
    return {
        "disruptions": DISRUPTION_ZONES,
        "tide_stations": [
            {"name": "Colombo Port", "lat": 6.94, "lon": 79.84, "level": "+1.2m", "trend": "rising"},
            {"name": "Suez South", "lat": 29.9, "lon": 32.5, "level": "-0.4m", "trend": "falling"}
        ],
        "wave_buoys": [
            {"lat": 5.0, "lon": 85.0, "height": "2.1m", "period": "8s"}
        ]
    }

@app.post("/calculate-route")
async def calculate_route(request: VoyageRequest):
    src = (request.source.lat, request.source.lon)
    dest = (request.destination.lat, request.destination.lon)
    
    # Run Dijkstra
    path, total_cost = dijkstra_search(src, dest, resolution=2)

    if not path:
        # Fallback to direct path if grid search fails (rare)
        path = [[src[0], src[1]], [dest[0], dest[1]]]
        status = "FAILED_OPTIMIZATION"
    else:
        # Ensure the exact source and destination are included
        path = [[src[0], src[1]]] + [list(p) for p in path] + [[dest[0], dest[1]]]
        status = "OPTIMIZED"

    # Identify if any part of the path is near a disruption for UI reporting
    disruption_name = None
    max_hazard = 0
    for p in path:
        for zone in DISRUPTION_ZONES:
            if haversine_distance((p[0], p[1]), (zone['lat'], zone['lon'])) < (zone['radius'] * 111):
                disruption_name = zone['name']
                max_hazard = zone['wave_height'] if 'wave_height' in zone else 4.0

    return {
        "status": status,
        "path": path,
        "disruption": disruption_name,
        "environmental_stats": {
            "avg_wave_height": f"{max_hazard if disruption_name else 1.2}m",
            "wind_speed": "22 knots" if disruption_name else "10 knots",
            "tide_impact": "Negligible"
        },
        "focus_ship_id": "123065"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)