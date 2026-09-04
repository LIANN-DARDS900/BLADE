from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any

from .models import OperationResult


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class PowerShellRunner:
    """Run one controlled PowerShell operation and parse its JSON result.

    The process is always launched with `-ExecutionPolicy Bypass`, and the
    command explicitly applies `Set-ExecutionPolicy Bypass -Scope Process`
    before invoking the operation script. No user or machine policy is changed.
    """

    def __init__(self, script_path: Path, log_callback=None) -> None:
        self.script_path = Path(script_path)
        self.log_callback = log_callback
        self._process_lock = threading.Lock()
        self._current_process: subprocess.Popen[str] | None = None

    def run_operation(
        self,
        operation: str,
        timeout: int = 180,
        parameters: dict[str, Any] | None = None,
    ) -> OperationResult:
        if os.name != "nt":
            return OperationResult(
                operation=operation,
                success=False,
                status="blocked",
                message="This operation requires Windows.",
                error_code="WINDOWS_REQUIRED",
                return_code=10,
            )
        if not self.script_path.exists():
            return OperationResult(
                operation=operation,
                success=False,
                status="failed",
                message=f"PowerShell operation script not found: {self.script_path}",
                error_code="SCRIPT_NOT_FOUND",
                return_code=11,
            )

        params = parameters or {}
        invoke_parts = [
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;",
            "$OutputEncoding = [System.Text.Encoding]::UTF8;",
            "Set-ExecutionPolicy Bypass -Scope Process -Force;",
            f"& {_ps_quote(str(self.script_path))}",
            "-Operation",
            _ps_quote(operation),
        ]
        for key, value in params.items():
            safe_key = "".join(ch for ch in str(key) if ch.isalnum() or ch in "_-")
            if isinstance(value, bool):
                if value:
                    invoke_parts.append(f"-{safe_key}")
            elif value is not None:
                invoke_parts.extend([f"-{safe_key}", _ps_quote(str(value))])

        command_text = " ".join(invoke_parts)
        command = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command_text,
        ]
        self._log(f"PowerShell operation: {operation}")

        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            with self._process_lock:
                self._current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creation_flags,
                )
            stdout, stderr = self._current_process.communicate(timeout=timeout)
            return_code = self._current_process.returncode or 0
        except subprocess.TimeoutExpired:
            # A timeout ends only the helper PowerShell process. It does not stop
            # BitLocker, SCCM services, or an already-started Windows operation.
            with self._process_lock:
                if self._current_process:
                    self._current_process.kill()
                    stdout, stderr = self._current_process.communicate()
            return OperationResult(
                operation=operation,
                success=False,
                status="failed",
                message=f"Operation timed out after {timeout} seconds.",
                error_code="OPERATION_TIMEOUT",
                return_code=12,
                raw_stdout=stdout,
                raw_stderr=stderr,
            )
        except OSError as exc:
            return OperationResult(
                operation=operation,
                success=False,
                status="failed",
                message=f"PowerShell could not be started: {exc}",
                error_code="POWERSHELL_START_FAILED",
                return_code=13,
                raw_stderr=str(exc),
            )
        finally:
            with self._process_lock:
                self._current_process = None

        payload = self._extract_json(stdout)
        if payload is None:
            combined = f"{stdout}\n{stderr}".lower()
            if "running scripts is disabled" in combined or "execution policy" in combined:
                message = "PowerShell execution was blocked by an effective policy. Process-level Bypass could not override the corporate policy."
                error_code = "POWERSHELL_POLICY_BLOCKED"
            elif "blocked by group policy" in combined or "applocker" in combined or "application control" in combined:
                message = "Windows application control blocked the PowerShell helper or operation script."
                error_code = "APPLICATION_CONTROL_BLOCKED"
            elif "access is denied" in combined or "unauthorizedaccessexception" in combined:
                message = "The operation was denied. Confirm Administrator elevation and local security policy."
                error_code = "ACCESS_DENIED"
            else:
                message = "The operation did not return valid structured output."
                error_code = "INVALID_OPERATION_OUTPUT"
            return OperationResult(
                operation=operation,
                success=False,
                status="failed",
                message=message,
                error_code=error_code,
                return_code=return_code or 14,
                raw_stdout=stdout,
                raw_stderr=stderr,
            )
        return OperationResult.from_payload(
            operation=operation,
            payload=payload,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
        )

    @staticmethod
    def _extract_json(stdout: str) -> dict[str, Any] | None:
        for line in reversed([item.strip() for item in stdout.splitlines() if item.strip()]):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
