from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .constants import LOG_DIR


class AuditLogger:
    """Append-only local audit trail for technician actions and operation results."""

    def __init__(self) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        stamp = datetime.now().strftime("%Y%m%d")
        self.text_path = LOG_DIR / f"assistant-{stamp}.log"
        self.jsonl_path = LOG_DIR / f"assistant-{stamp}.jsonl"

    def write_event(self, message: str, level: str = "info", **extra: Any) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] [{level.upper():7}] {message}\n"
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "type": "event",
            "level": level,
            "message": message,
        }
        payload.update(extra)
        self._append(self.text_path, line)
        self._append(self.jsonl_path, json.dumps(payload, ensure_ascii=False) + "\n")

    def write_result(self, operation: str, result: Any) -> None:
        timestamp = getattr(result, "timestamp", datetime.now().isoformat(timespec="seconds"))
        payload = {
            "timestamp": timestamp,
            "type": "operation_result",
            "operation": operation,
            "success": bool(getattr(result, "success", False)),
            "status": str(getattr(result, "status", "unknown")),
            "message": str(getattr(result, "message", "")),
            "errorCode": getattr(result, "error_code", None),
            "returnCode": int(getattr(result, "return_code", 0)),
            "data": getattr(result, "data", {}) or {},
        }
        self._append(self.jsonl_path, json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def _append(path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(content)
        except OSError:
            # Logging must never crash or block the technician workflow.
            pass
