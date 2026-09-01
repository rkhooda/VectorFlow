# Frontend / Dashboard (Flask)

Entry point: `dashboard/app.py`. Run: `python dashboard/app.py` (serves on
`http://127.0.0.1:5000/`, port from `config.yaml`). Start the backend first
(`uvicorn backend.app.main:app --port 8000`).

The dashboard is intentionally thin: it renders pages and shows data fetched
from the backend. **All analysis logic lives in the backend** — if a view
needs new data, add a backend endpoint, not dashboard logic.

The browser talks only to Flask (same origin). Flask forwards a whitelisted
set of `/api/*` paths to FastAPI through `api_client.py`, passing status
codes (404/409) through — so no CORS setup exists anywhere.

## Layout

```
dashboard/
├── app.py           # Flask routes
├── api_client.py    # requests wrapper around the backend API (localhost)
├── templates/       # Jinja2 templates — structural HTML only for now
│   ├── base.html
│   └── index.html   # placeholder sections for every PS-required panel
└── static/          # css/ js/ — vendored assets only (offline), no CDN
```

## Panels (mapped to problem-statement requirements)

`index.html` already contains one placeholder `<section>` per panel:

| Section id           | Shows                                   | Backend endpoint |
|----------------------|-----------------------------------------|------------------|
| `replay-status`      | Input/replay status & progress          | `/api/session/status` |
| `network-state`      | Current network state                   | `/api/state/current` |
| `attack-probability` | Infiltration/attack probability         | `/api/forecast` |
| `forecast-timeline`  | Forecast timeline over the horizon      | `/api/forecast` |
| `attack-stage`       | Predicted MITRE ATT&CK stage            | `/api/stage` |
| `explanations`       | Important contributing features/reasons | `/api/explanations` |
| `flagged-flows`      | Flagged/suspicious traffic              | `/api/flows/flagged` |
| `traffic-summary`    | Basic traffic information               | `/api/traffic/summary` |

## Update model

Plain JavaScript polling (`static/js/dashboard.js`): `fetch` + `setInterval`
every 2 s (the replay cadence) against `/api/session/status`, then all result
endpoints in parallel while the session is replaying. Polling stops when the
replay completes or no session exists, and resumes/re-attaches on page load.
Backend-down (502) shows an error banner and keeps the last rendered data;
404/409 render as idle/not-ready states. No page reloads, no WebSockets.

The timeline's observed-probability history and the stage progression trail
are accumulated client-side per session (the backend only serves the current
position), so they reset on a page reload mid-replay.

## Design

The current templates and `static/css/style.css` are **functional only**.
The UI/UX designer provides the actual visual design later; it drops into
`templates/` + `static/css/` without touching routes, the API client,
`dashboard.js`'s data flow, or the backend.
