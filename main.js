const express = require('express');
const cors = require('cors');
const { randomUUID } = require('crypto');

const app = express();
const NOAA_API_TOKEN = process.env.NOAA_API_TOKEN || 'WovUqqdkOAhuNTcGReDULESBmmqtFmRk';

app.use(cors());
app.use(express.json());

const EXTENDED_LAND_ZONES = [
  { name: 'Africa', min_lat: -35, max_lat: 37, min_lon: -18, max_lon: 51 },
  { name: 'Americas_North', min_lat: 15, max_lat: 75, min_lon: -170, max_lon: -50 },
  { name: 'Americas_South', min_lat: -56, max_lat: 15, min_lon: -82, max_lon: -34 },
  { name: 'Eurasia_Main', min_lat: 35, max_lat: 75, min_lon: -10, max_lon: 145 },
  { name: 'Australia', min_lat: -44, max_lat: -10, min_lon: 112, max_lon: 154 },
  { name: 'India_Sub', min_lat: 8, max_lat: 30, min_lon: 68, max_lon: 90 },
  { name: 'Arabia', min_lat: 12, max_lat: 32, min_lon: 34, max_lon: 60 },
  { name: 'Greenland', min_lat: 60, max_lat: 84, min_lon: -73, max_lon: -12 }
];

const SEA_LANES = [
  { name: 'Suez Canal', lat_range: [27, 32], lon_range: [31, 33] },
  { name: 'Panama Canal', lat_range: [8.5, 9.5], lon_range: [-80, -79] },
  { name: 'Malacca Strait', lat_range: [1, 6], lon_range: [95, 104] },
  { name: 'English Channel', lat_range: [49, 51], lon_range: [-5, 2] },
  { name: 'Bab-el-Mandeb', lat_range: [11.5, 13.5], lon_range: [42.5, 44] }
];

const GATEWAY_WAYPOINTS = {
  Suez: [30.0, 32.5],
  Panama: [9.0, -79.8],
  Malacca: [2.0, 102.0],
  Gibraltar: [36.0, -5.5],
  Bering: [66.0, -168.0]
};

const DEFAULT_DISRUPTION_ZONES = [
  { id: randomUUID(), name: 'Cyclonic Activity Alpha', lat: 12.5, lon: 82.0, radius: 4.5, penalty: 600 },
  { id: randomUUID(), name: 'Port Congestion Area', lat: 24.5, lon: 54.0, radius: 2.0, penalty: 300 }
];

let DISRUPTION_ZONES = DEFAULT_DISRUPTION_ZONES.map((zone) => ({ ...zone }));

function isLandLocked(lat, lon) {
  for (const lane of SEA_LANES) {
    if (lat >= lane.lat_range[0] && lat <= lane.lat_range[1] && lon >= lane.lon_range[0] && lon <= lane.lon_range[1]) {
      return false;
    }
  }

  return EXTENDED_LAND_ZONES.some((box) => lat >= box.min_lat && lat <= box.max_lat && lon >= box.min_lon && lon <= box.max_lon);
}

function haversineDistance(p1, p2) {
  const lat1 = (p1[0] * Math.PI) / 180;
  const lon1 = (p1[1] * Math.PI) / 180;
  const lat2 = (p2[0] * Math.PI) / 180;
  const lon2 = (p2[1] * Math.PI) / 180;

  const dlat = lat2 - lat1;
  const dlon = lon2 - lon1;
  const a = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(a));
}

function getDisruptionImpact(lat, lon) {
  let penalty = 0;
  for (const zone of DISRUPTION_ZONES) {
    const dist = haversineDistance([lat, lon], [zone.lat, zone.lon]);
    if (dist < zone.radius * 111) {
      const proximity = 1 - dist / (zone.radius * 111);
      penalty += zone.penalty * proximity ** 1.5;
    }
  }
  return penalty;
}

function roundCoord(value, resolution) {
  return Math.round(value / resolution) * resolution;
}

function aStarRoute(start, end, resolution = 0.5) {
  const startNode = [roundCoord(start[0], resolution), roundCoord(start[1], resolution)];
  const endNode = [roundCoord(end[0], resolution), roundCoord(end[1], resolution)];

  const openSet = [{ priority: haversineDistance(startNode, endNode), cost: 0, coord: startNode, path: [] }];
  const visited = new Map();
  let iterations = 0;

  while (openSet.length > 0 && iterations < 10000) {
    iterations += 1;
    openSet.sort((a, b) => a.priority - b.priority);
    const currentNode = openSet.shift();
    const { cost, coord, path } = currentNode;
    const currentKey = `${coord[0]},${coord[1]}`;

    if (coord[0] === endNode[0] && coord[1] === endNode[1]) {
      return { path: [...path, coord], cost };
    }

    if (visited.has(currentKey) && visited.get(currentKey) <= cost) {
      continue;
    }
    visited.set(currentKey, cost);

    for (const dlat of [-resolution, 0, resolution]) {
      for (const dlon of [-resolution, 0, resolution]) {
        if (dlat === 0 && dlon === 0) continue;

        const neighbor = [roundCoord(coord[0] + dlat, resolution), roundCoord(coord[1] + dlon, resolution)];
        if (neighbor[0] < -70 || neighbor[0] > 80 || neighbor[1] < -180 || neighbor[1] > 180) continue;
        if (isLandLocked(neighbor[0], neighbor[1])) continue;

        const distStep = haversineDistance(coord, neighbor);
        const hazardCost = getDisruptionImpact(neighbor[0], neighbor[1]);
        const newCost = cost + distStep + (hazardCost * distStep) / 5;
        const heuristic = haversineDistance(neighbor, endNode);

        openSet.push({
          priority: newCost + heuristic,
          cost: newCost,
          coord: neighbor,
          path: [...path, coord]
        });
      }
    }
  }

  return { path: null, cost: 0 };
}

function routeViaGateway(src, dest, gatewayName) {
  const gateway = GATEWAY_WAYPOINTS[gatewayName];
  if (!gateway) return { path: null, cost: 0 };

  const firstLeg = aStarRoute(src, gateway);
  if (!firstLeg.path) return { path: null, cost: 0 };

  const secondLeg = aStarRoute(gateway, dest);
  if (!secondLeg.path) return { path: null, cost: 0 };

  const combinedPath = [...firstLeg.path, ...secondLeg.path.slice(1)];
  return { path: combinedPath, cost: firstLeg.cost + secondLeg.cost };
}

app.get('/system/status', (req, res) => {
  res.json({
    status: 'Operational',
    active_hazards: DISRUPTION_ZONES.length,
    api_connected: Boolean(NOAA_API_TOKEN),
    mode: 'High Precision'
  });
});

app.get('/zones', (req, res) => {
  res.json(DISRUPTION_ZONES);
});

app.post('/zones', (req, res) => {
  const { name, lat, lon, radius = 5.0, penalty = 500 } = req.body;
  if (typeof name !== 'string' || typeof lat !== 'number' || typeof lon !== 'number') {
    return res.status(400).json({ message: 'Invalid zone payload' });
  }

  const newZone = { id: randomUUID(), name, lat, lon, radius, penalty };
  DISRUPTION_ZONES.push(newZone);
  res.json(newZone);
});

app.delete('/zones', (req, res) => {
  DISRUPTION_ZONES = DEFAULT_DISRUPTION_ZONES.map((zone) => ({ ...zone }));
  res.json({ message: 'Hazards reset to default state.' });
});

app.post('/calculate-voyage', (req, res) => {
  const { source, destination } = req.body;
  if (!source || !destination || typeof source.lat !== 'number' || typeof source.lon !== 'number' || typeof destination.lat !== 'number' || typeof destination.lon !== 'number') {
    return res.status(400).json({ message: 'Invalid voyage request payload' });
  }

  const src = [source.lat, source.lon];
  const dest = [destination.lat, destination.lon];

  const statusPrefix = isLandLocked(src[0], src[1]) || isLandLocked(dest[0], dest[1]) ? 'PORT_ADJACENT' : 'DEEP_SEA';
  let result = aStarRoute(src, dest, 0.5);

  if (!result.path) {
    let fallbackAttempts = [];
    if (src[1] < -30 && dest[1] > 20) fallbackAttempts = ['Panama', 'Suez'];
    else if (src[1] > 20 && dest[1] < -30) fallbackAttempts = ['Suez', 'Panama'];
    else if (src[0] > 80 && dest[0] < 50) fallbackAttempts = ['Malacca', 'Suez'];
    else if (Math.abs(src[0] - dest[0]) > 20 && Math.abs(src[1] - dest[1]) > 100) fallbackAttempts = ['Panama', 'Suez'];

    for (const gateway of fallbackAttempts) {
      result = routeViaGateway(src, dest, gateway);
      if (result.path) break;
    }
  }

  if (!result.path) {
    const directDistance = haversineDistance(src, dest);
    return res.json({
      status: 'FAILED',
      path: [src, dest],
      message: 'Routing engine could not find a pure water path. Connectivity may be obstructed.',
      distance_km: Math.round(directDistance * 100) / 100
    });
  }

  const finalPath = [src, ...result.path.slice(1, -1), dest].map((point) => [point[0], point[1]]);
  const distanceKm = finalPath.reduce((sum, _, index) => {
    if (index === 0) return 0;
    return sum + haversineDistance(finalPath[index - 1], finalPath[index]);
  }, 0);

  res.json({
    status: 'SUCCESS',
    path: finalPath,
    distance_km: Math.round(distanceKm * 100) / 100,
    cost_index: Math.round(result.cost * 100) / 100,
    message: `Optimal maritime route established (${statusPrefix}).`
  });
});

const PORT = process.env.PORT || 8000;
app.listen(PORT, () => {
  console.log(`CargoWave JavaScript backend running on http://localhost:${PORT}`);
});
