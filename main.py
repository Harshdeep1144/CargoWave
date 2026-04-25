from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import math
import uvicorn

app = FastAPI(title="Smart Supply Chain - Maritime Brain")

# --- CORS SETUP (CRITICAL FOR CONNECTION) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows the Canvas HTML to talk to your local server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MOCK DATA: Disruption Zones ---
# These simulate areas where traffic or weather is causing issues
DISRUPTION_ZONES = [
    {"name": "Tropical Storm Alpha", "lat": 8.0, "lon": 73.0, "radius": 4.0}, 
    {"name": "Suez Congestion", "lat": 29.9, "lon": 32.5, "radius": 2.0}
]

class Location(BaseModel):
    lat: float
    lon: float

class VoyageRequest(BaseModel):
    source: Location
    destination: Location

def get_distance(p1, p2):
    """Simple Euclidean distance for prototype logic"""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

@app.post("/calculate-route")
async def calculate_route(request: VoyageRequest):
    src = request.source
    dest = request.destination
    
    # 1. Determine the standard "Commercial Shipping Lane" waypoints
    if dest.lat < 10: # Singapore logic (Traveling East)
        path = [[src.lat, src.lon], [5.5, 80.0], [5.8, 95.0], [dest.lat, dest.lon]]
    else: # Rotterdam logic (Traveling West through Suez)
        path = [[src.lat, src.lon], [12.5, 43.3], [29.9, 32.5], [dest.lat, dest.lon]]

    disruption_found = None
    optimized_path = []

    # 2. Analyze the path for disruptions and apply "Dynamic Optimization"
    for point in path:
        threat = None
        for zone in DISRUPTION_ZONES:
            if get_distance(point, [zone['lat'], zone['lon']]) < zone['radius']:
                threat = zone
        
        if threat:
            disruption_found = threat
            # RESILIENCE LOGIC: If a bottleneck is detected, calculate a detour
            # Pushing the waypoint 8 degrees south to move into safer, open water
            optimized_path.append([point[0] - 8.0, point[1]])
        else:
            optimized_path.append(point)

    # 3. Return the optimized voyage plan to the Android interface
    return {
        "status": "OPTIMIZED" if disruption_found else "CLEAR",
        "path": optimized_path,
        "disruption": disruption_found['name'] if disruption_found else None,
        # We can also return specific MarineTraffic IDs for the app to focus on
        "focus_ship_id": "123065" 
    }

if __name__ == "__main__":
    # Run the server on localhost port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)