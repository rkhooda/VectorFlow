# Attack Intelligence module

Owner: Attack Intelligence teammate.

Maps forecasts to a predicted MITRE ATT&CK stage, produces explanations
(driving features / reasons) and flags suspicious flows.

Implement the contract described in `docs/integration.md` using the Pydantic
models from `contracts/`. The backend imports this package in-process; a mock
in `backend/app/services/` stands in until this module is ready.
