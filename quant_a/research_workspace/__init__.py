"""Lightweight, local-first research workflow utilities.

The module brings watchlists, strategy snapshots and an append-only activity
trail into the Streamlit application without adding a database dependency.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List


class ResearchWorkspace:
    """Persist research state as small, human-readable local files."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.watchlist_file = os.path.join(root, "watchlist.json")
        self.snapshots_file = os.path.join(root, "strategy_snapshots.json")
        self.audit_file = os.path.join(root, "activity.jsonl")

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _read_json(path: str, fallback: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return fallback

    @staticmethod
    def _write_json(path: str, payload: Any) -> None:
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(temp_path, path)

    def add_watchlist(self, codes: Iterable[str], source: str = "manual") -> List[Dict[str, Any]]:
        existing = self._read_json(self.watchlist_file, [])
        by_code = {str(item.get("code", "")): item for item in existing if item.get("code")}
        now = self._now()
        for code in codes:
            normalized = str(code).strip().zfill(6)
            if not normalized:
                continue
            previous = by_code.get(normalized, {})
            by_code[normalized] = {
                "code": normalized,
                "source": source,
                "added_at": previous.get("added_at", now),
                "updated_at": now,
                "status": "researching",
            }
        rows = sorted(by_code.values(), key=lambda item: item.get("updated_at", ""), reverse=True)
        self._write_json(self.watchlist_file, rows)
        self.audit("WATCHLIST_UPDATE", f"Added {len(list(codes))} candidates from {source}", {"source": source})
        return rows

    def watchlist(self) -> List[Dict[str, Any]]:
        return self._read_json(self.watchlist_file, [])

    def save_snapshot(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        snapshots = self._read_json(self.snapshots_file, [])
        record = {"snapshot_id": f"SNAP-{len(snapshots) + 1:04d}", "created_at": self._now(), **summary}
        snapshots.insert(0, record)
        self._write_json(self.snapshots_file, snapshots[:100])
        self.audit("STRATEGY_SNAPSHOT", f"Saved {record['snapshot_id']}", record)
        return record

    def snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._read_json(self.snapshots_file, [])[:limit]

    def audit(self, event: str, message: str, context: Dict[str, Any] | None = None) -> None:
        row = {"time": self._now(), "event": event, "message": message, "context": context or {}}
        with open(self.audit_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def activity(self, limit: int = 30) -> List[Dict[str, Any]]:
        try:
            with open(self.audit_file, "r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        return list(reversed(rows[-limit:]))
