# Evidence ledger

VectorFlow uses a small local hash-linked ledger because the SIH demo must run
offline. It is an audit layer after forecasting and attack intelligence, not a
dependency of prediction.

Each alert writes a compact canonical payload containing:

- alert ID and event timestamp;
- forecast probability and predicted stage;
- model version; and
- the model-derived top feature contributions.

The SHA-256 payload hash is stored in a block with the previous block hash.
`LocalSecurityEvidenceLedger.verify()` recalculates the evidence hash and
rebuilds every block hash from genesis to the requested record. Any payload or
link modification returns `verified: false`.

Raw traffic, PCAPs, payloads, and large datasets are never written to the
ledger. If `data/blockchain/ledger.json` cannot be read or written, the alert
is retained with `ledger_status: unavailable` and the forecast remains usable.

Set `blockchain.enabled: false` to disable the audit layer explicitly. The
default path is local and ignored by Git.
