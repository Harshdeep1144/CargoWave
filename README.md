# CargoWave Smart Supply Chain

This project is a maritime logistics simulator for cargo ships with live disruption zone simulation, hazard-aware route optimization, and environmental risk signaling.

## What it includes

- `index.html` — interactive route planner and simulation dashboard
- `main.py` — FastAPI backend with hazard-aware A* routing and disruption zone management
- `requirements.txt` — Python dependencies

## Run locally

1. Activate your Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the backend:
   ```bash
   python main.py
   ```
4. Open `index.html` in your browser.

## API key setup

This app can optionally use external weather and tidal services.

### WhereTr API

1. Sign up at the WhereTr developer portal.
2. Create an API key.
3. Set the environment variable in your shell:
   ```bash
   set WHERETR_API_KEY=your_key_here
   ```

### Tidal Disruption API

1. Sign up for the tidal provider of your choice.
2. Obtain the API key.
3. Set the environment variable:
   ```bash
   set TIDAL_API_KEY=your_key_here
   ```

## Notes

- The backend supports `/zones` endpoints to add, list, and reset disruption zones.
- Clicking on the map auto-fills the disruption zone form.
- The route optimizer avoids hazard zones and returns recommended route metrics.

## Important

If you want the app to load real weather and tide data, install `requests` (already included) and add valid API keys.
