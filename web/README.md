# WatSen — landing page and water intelligence workspace

    npm install && npm run dev      # http://localhost:5173

Needs the API on :8000 (`make api` from the repo root).

- `VITE_API_BASE` — API origin, defaults to `http://localhost:8000`

The root route opens the public landing page. Its calls to action open the
workspace using hash routes, so static preview hosting needs no route rewrites.

- `#/workspace/Network` — catchment schematic, watchlist, forecast and intervention lab
- `#/workspace/Evidence` — photo assessment, reach-specific review queue and evidence ledger
- `#/workspace/One%20Health` — linked environmental signals and evidence-grounded brief
- `#/workspace/Standards` — FHIR preflight, provenance and model card

The sky-blue design uses DM Sans and Plus Jakarta Sans with local supplied
artwork in `public/assets`. System sans-serif remains available offline.
Animations respect reduced-motion preferences. Search supports Ctrl/Cmd+K,
arrow keys, Enter and Escape. The map is a keyboard-accessible geographic
schematic, not a geographic basemap; no map provider key is required.

The included API data is synthetic demonstration evidence. Forecasts and
intervention outputs must not be represented as validated operational advice.

Production check: `npm run build`. Preview: `npm run preview -- --port 4173`.
