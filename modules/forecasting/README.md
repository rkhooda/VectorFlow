# ML Forecasting module

Owner: ML Forecasting teammate.

Learns past network behaviour from time-based network states and predicts
future attack/infiltration probability over a forecast horizon.

Implement the contract described in `docs/integration.md` using the Pydantic
models from `contracts/`. The backend imports this package in-process; a mock
in `backend/app/services/` stands in until this module is ready.
