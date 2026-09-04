from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Status(str, Enum):
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    WARNING = "warning"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCESS = "success"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class OperationResult:
    operation: str
    success: bool
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    return_code: int = 0
    raw_stdout: str = ""
    raw_stderr: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_payload(
        cls,
        operation: str,
        payload: dict[str, Any],
        return_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> "OperationResult":
        return cls(
            operation=operation,
            success=bool(payload.get("success", return_code == 0)),
            status=str(payload.get("status", "unknown")),
            message=str(payload.get("message", "Operation completed.")),
            data=dict(payload.get("data") or {}),
            error_code=payload.get("errorCode"),
            return_code=return_code,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )
