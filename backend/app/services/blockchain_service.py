"""Offline tamper-evident evidence ledger.

This is intentionally a tiny local blockchain rather than a public-chain
dependency: each JSON block contains the canonical evidence hash, the hash of
the previous block, and its own hash. The detailed traffic remains off-chain.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts import (
    AttackStagePrediction,
    BlockchainVerification,
    EvidenceRecord,
    Explanation,
    SecurityAlert,
)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"unsupported evidence value: {type(value)!r}")


def canonical_payload(alert: SecurityAlert, explanation: Explanation) -> dict[str, Any]:
    """Build the exact compact payload that is hashed and audited."""
    return {
        "alert_id": alert.alert_id,
        "timestamp": alert.timestamp.astimezone(timezone.utc).isoformat(),
        "attack_probability": round(alert.attack_probability, 8),
        "predicted_stage": alert.predicted_stage,
        "mitre_technique": alert.mitre_technique,
        "model_version": alert.model_version,
        "important_features": [
            {"feature": item.feature, "contribution": round(item.contribution, 8)}
            for item in explanation.top_features
        ],
    }


def evidence_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, default=_json_default, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class LocalSecurityEvidenceLedger:
    """Small persistent local chain with idempotent alert writes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def _write(self, blocks: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(blocks, indent=2, sort_keys=True, default=_json_default))

    def record(self, alert: SecurityAlert, explanation: Explanation) -> EvidenceRecord:
        payload = canonical_payload(alert, explanation)
        digest = evidence_hash(payload)
        with self._lock:
            blocks = self._read()
            for block in blocks:
                if block["payload"]["alert_id"] == alert.alert_id:
                    return self._record_from_block(block, digest)
            previous = blocks[-1]["block_hash"] if blocks else "0" * 64
            block_body = {
                "index": len(blocks),
                "recorded_at": datetime.now(timezone.utc),
                "payload": payload,
                "evidence_hash": digest,
                "previous_hash": previous,
            }
            block_hash = hashlib.sha256(
                json.dumps(block_body, default=_json_default, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            block = {**block_body, "block_hash": block_hash}
            blocks.append(block)
            self._write(blocks)
            return self._record_from_block(block, digest)

    def _record_from_block(self, block: dict[str, Any], digest: str) -> EvidenceRecord:
        payload = block["payload"]
        features = [
            {"feature": item["feature"], "contribution": item["contribution"]}
            for item in payload["important_features"]
        ]
        return EvidenceRecord(
            alert_id=payload["alert_id"],
            timestamp=payload["timestamp"],
            attack_probability=payload["attack_probability"],
            predicted_stage=payload["predicted_stage"],
            mitre_technique=payload["mitre_technique"],
            model_version=payload["model_version"],
            important_features=features,
            evidence_hash=digest,
            ledger_status="recorded",
            transaction_id=block["block_hash"],
        )

    def verify(self, alert_id: str, explanation: Explanation | None = None) -> BlockchainVerification:
        with self._lock:
            blocks = self._read()
        block = next((b for b in blocks if b["payload"]["alert_id"] == alert_id), None)
        if block is None:
            return BlockchainVerification(alert_id=alert_id, verified=False, message="Evidence record not found")
        stored = block["evidence_hash"]
        recalculated = evidence_hash(block["payload"])
        chain_valid = True
        previous = "0" * 64
        for candidate in blocks:
            if candidate["previous_hash"] != previous:
                chain_valid = False
                break
            body = {k: candidate[k] for k in ("index", "recorded_at", "payload", "evidence_hash", "previous_hash")}
            expected = hashlib.sha256(json.dumps(body, default=_json_default, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if candidate["block_hash"] != expected:
                chain_valid = False
                break
            previous = candidate["block_hash"]
        verified = stored == recalculated and chain_valid
        return BlockchainVerification(
            alert_id=alert_id,
            verified=verified,
            evidence_hash=recalculated,
            stored_hash=stored,
            message="Evidence Verified — record has not been modified" if verified else "Evidence Modified or chain is invalid",
        )


def get_ledger(config: dict) -> LocalSecurityEvidenceLedger | None:
    if not config.get("enabled", True):
        return None
    return LocalSecurityEvidenceLedger(config.get("ledger_path", "data/blockchain/ledger.json"))
