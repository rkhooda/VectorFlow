# Data Pipeline module

Owner: Data Pipeline teammate.

Turns raw PCAP/CSV input into cleaned, feature-extracted, time-windowed
network states.

Implement the contract described in `docs/integration.md` using the Pydantic
models from `contracts/`. The backend imports this package in-process; a mock
in `backend/app/services/` stands in until this module is ready.
