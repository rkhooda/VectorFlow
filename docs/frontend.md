# Frontend / Dashboard (Flask)

Entry point: `dashboard/app.py`. Run: `python dashboard/app.py` (serves on
`http://127.0.0.1:5000/`, port from `config.yaml`).

The dashboard is intentionally thin: it renders pages and shows data fetched
from the backend. **All analysis logic lives in the backend** — if a view
needs new data, add a backend endpoint, not dashboard logic.

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

Plain JavaScript polling (`fetch` + `setInterval`, in `static/js/`) against
the backend endpoints — matches the replay cadence and needs no extra
dependencies. No WebSockets unless polling proves insufficient.

## Design

The current templates are **structural placeholders only**. The UI/UX
designer provides the actual visual design later; it drops into
`templates/` + `static/css/` without touching routes, the API client, or the
backend. Do not add speculative styling before then.
