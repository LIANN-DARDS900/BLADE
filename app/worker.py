from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import threading
import time
from typing import Any

from PySide6.QtCore import QThread, Signal

from .constants import LOG_DIR, STATE_PATH
from .models import OperationResult
from .powershell import PowerShellRunner


class WorkflowWorker(QThread):
    log = Signal(str, str)
    stage = Signal(str, str)
    result = Signal(object)
    progress = Signal(int)
    finished_state = Signal(str, str)

    def __init__(self, runner: PowerShellRunner, config: dict[str, Any], workflow: str) -> None:
        super().__init__()
        self.runner = runner
        self.config = config
        self.workflow = workflow
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self._started_at = datetime.now()

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.pause_event.clear()
        self.log.emit("Cancel requested. The current safe operation will finish first.", "warning")

    def request_pause(self, paused: bool) -> None:
        if paused:
            self.pause_event.set()
            self.log.emit("Pause requested. No new operation will start.", "warning")
        else:
            self.pause_event.clear()
            self.log.emit("Workflow resumed.", "info")

    def run(self) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            if self.workflow == "preflight":
                self._run_preflight_only()
            elif self.workflow == "dry_run":
                self._run_dry_run()
            elif self.workflow == "repair":
                self._run_repair()
            else:
                self._run_deployment()
        except Exception as exc:  # last-resort UI protection
            self.log.emit(f"Unexpected workflow error: {exc}", "error")
            self.finished_state.emit("failed", str(exc))

    def _run_preflight_only(self) -> None:
        self.stage.emit("PREFLIGHT", "Checking machine readiness")
        result = self._execute("preflight", timeout=90)
        checks = list(result.data.get("checks") or [])
        if checks:
            ready_count = sum(1 for check in checks if str(check.get("status")) in {"ready", "success", "ok"})
            readiness_score = round((ready_count / len(checks)) * 100)
        else:
            readiness_score = 0
        self.progress.emit(readiness_score)
        final = "ready" if result.success else "blocked"
        self.finished_state.emit(final, result.message)


    def _run_dry_run(self) -> None:
        """Collect evidence only. This workflow never starts repair, policy sync, or gpupdate."""
        self.stage.emit("PREFLIGHT", "Running read-only readiness detection")
        preflight = self._execute("preflight", timeout=90)
        self.progress.emit(25)
        if self._stop_requested():
            return

        self.stage.emit("SCCM_HEALTH", "Reading SCCM health without remediation")
        self._execute("sccm_health", timeout=90)
        self.progress.emit(45)
        if self._stop_requested():
            return

        if bool(self.config.get("enable_sccm_log_evidence", True)):
            self.stage.emit("POLICY_WAIT", "Reading sanitized SCCM policy and BitLocker log evidence")
            self._execute("sccm_log_evidence", timeout=120)
        self.progress.emit(65)
        if self._stop_requested():
            return

        if bool(self.config.get("enable_ccmcache_discovery", True)):
            self.stage.emit("POLICY_WAIT", "Inspecting SCCM cache for relevant deployment content")
            self._execute("ccmcache_discovery", timeout=180)
        self.progress.emit(85)
        if self._stop_requested():
            return

        self.stage.emit("BITLOCKER_MONITOR", "Reading current BitLocker state")
        self._execute("bitlocker_status", timeout=90)
        self.progress.emit(100)
        state = "ready" if preflight.data.get("minimumReady") else "waiting"
        self.finished_state.emit(
            state,
            "Dry-run evidence collection completed. No repair, SCCM policy trigger, gpupdate, reboot, or BitLocker modification was started.",
        )

    def _run_repair(self) -> None:
        self.stage.emit("SCCM_REPAIR", "Running safe SCCM remediation")
        self.progress.emit(10)
        before = self._execute("sccm_health", timeout=90)
        if before.data.get("healthy"):
            self.progress.emit(100)
            self.finished_state.emit("success", "SCCM client is already healthy.")
            return
        if self._stop_requested():
            return
        self.progress.emit(35)
        self._execute("repair_sccm_basic", timeout=180)
        if self._stop_requested():
            return
        self.progress.emit(60)
        after_basic = self._execute("sccm_health", timeout=90)
        if after_basic.data.get("healthy"):
            self.progress.emit(100)
            self.finished_state.emit("success", "SCCM basic remediation succeeded.")
            return
        self.progress.emit(75)
        self._execute("ccmeval", timeout=960)
        self.progress.emit(90)
        final = self._execute("sccm_health", timeout=90)
        self.progress.emit(100)
        if final.data.get("healthy"):
            self.finished_state.emit("success", "SCCM client health evaluation succeeded.")
        else:
            self.finished_state.emit(
                "blocked",
                "SCCM remains unhealthy. Deep ccmrepair requires explicit technician review.",
            )

    def _run_deployment(self) -> None:
        sequence_progress = {
            "preflight": 5,
            "sccm_health": 15,
            "sync": 35,
            "gpupdate": 48,
            "policy": 60,
            "encryption": 75,
            "complete": 100,
        }
        self._save_state("STARTING")
        self.stage.emit("PREFLIGHT", "Detecting Ethernet, TPM, SCCM and BitLocker")
        preflight = self._execute("preflight", timeout=90)
        self.progress.emit(sequence_progress["preflight"])
        bitlocker_at_start = dict(preflight.data.get("bitlocker") or {})
        if bitlocker_at_start.get("fullyEncrypted") and bitlocker_at_start.get("protectionOn"):
            self.progress.emit(100)
            self._save_state("SUCCESS", bitlocker_at_start)
            self.finished_state.emit("success", "This device is already fully encrypted and protected. No deployment action was required.")
            return
        if not preflight.success or not preflight.data.get("minimumReady", False):
            self.finished_state.emit("blocked", preflight.message)
            return
        if self._stop_requested():
            return

        self.stage.emit("SCCM_HEALTH", "Checking Configuration Manager client")
        health = self._execute("sccm_health", timeout=90)
        self.progress.emit(sequence_progress["sccm_health"])
        if not health.data.get("healthy", False):
            self.log.emit("SCCM is unhealthy. Starting safe basic remediation.", "warning")
            self._execute("repair_sccm_basic", timeout=180)
            health = self._execute("sccm_health", timeout=90)
            if not health.data.get("healthy", False):
                self.log.emit("Basic remediation was insufficient. Running CcmEval once.", "warning")
                self._execute("ccmeval", timeout=960)
                health = self._execute("sccm_health", timeout=90)
            if not health.data.get("healthy", False):
                self.finished_state.emit(
                    "blocked",
                    "SCCM is still unhealthy. Use Diagnostics before continuing.",
                )
                return
        if self._stop_requested():
            return

        sync_op = "adaptive_sync" if self.workflow == "full" else "fast_sync"
        sync_label = "adaptive SCCM refresh" if sync_op == "adaptive_sync" else "focused BitLocker policy sync"
        self.stage.emit("POLICY_SYNC", f"Running {sync_label}")
        sync_result = self._execute(sync_op, timeout=300)
        self._log_schedule_actions(sync_result)
        self.progress.emit(sequence_progress["sync"])
        if not sync_result.success:
            self.finished_state.emit("blocked", sync_result.message)
            return
        if self._stop_requested():
            return

        self.stage.emit("GROUP_POLICY", "Applying computer Group Policy once")
        gp = self._execute("gpupdate", timeout=180)
        self.progress.emit(sequence_progress["gpupdate"])
        if not gp.success:
            self.log.emit("Group Policy returned a warning; policy monitoring will continue.", "warning")
        if self._stop_requested():
            return

        self.stage.emit("POLICY_WAIT", "Waiting for enterprise BitLocker policy evidence")
        self.progress.emit(sequence_progress["policy"])
        policy_started = time.monotonic()
        policy_deadline = policy_started + int(self.config["policy_wait_seconds"])
        retry_schedule = [int(value) for value in self.config.get("policy_retry_seconds", [300, 900])]
        max_attempts = max(1, int(self.config.get("max_policy_attempts", 3)))
        retry_index = 0
        policy_attempts = 1
        policy_seen = False
        while time.monotonic() < policy_deadline:
            if self._stop_requested():
                return
            evidence = self._execute("policy_evidence", timeout=90)
            if evidence.data.get("policyFound") or evidence.data.get("encryptionStarted"):
                policy_seen = True
                break

            elapsed = int(time.monotonic() - policy_started)
            if (
                retry_index < len(retry_schedule)
                and policy_attempts < max_attempts
                and elapsed >= retry_schedule[retry_index]
            ):
                policy_attempts += 1
                retry_index += 1
                self.stage.emit("POLICY_SYNC", f"Focused machine-policy retry {policy_attempts} of {max_attempts}")
                retry = self._execute("policy_request", timeout=180)
                if not retry.success:
                    self.log.emit("The focused policy retry returned a warning; monitoring continues.", "warning")
                self.stage.emit("POLICY_WAIT", "Waiting for enterprise BitLocker policy evidence")
                continue

            self.log.emit("No BitLocker policy evidence yet. Waiting before the next check.", "waiting")
            if not self._interruptible_wait(int(self.config["policy_poll_seconds"])):
                return
        if not policy_seen:
            if bool(self.config.get("enable_sccm_log_evidence", True)):
                self._execute("sccm_log_evidence", timeout=120)
            if bool(self.config.get("enable_ccmcache_discovery", True)):
                self._execute("ccmcache_discovery", timeout=180)
            self.finished_state.emit(
                "waiting",
                "Machine is healthy, but BitLocker policy was not detected before the timeout. Diagnostic evidence was collected.",
            )
            return

        self.stage.emit("BITLOCKER_MONITOR", "Monitoring encryption without triggering heavy SCCM actions")
        self.progress.emit(sequence_progress["encryption"])
        global_deadline = time.monotonic() + int(float(self.config["global_timeout_hours"]) * 3600)
        last_pct = -1
        while time.monotonic() < global_deadline:
            if self._stop_requested():
                return
            bitlocker = self._execute("bitlocker_status", timeout=90)
            data = bitlocker.data
            pct = int(data.get("encryptionPercentage") or 0)
            self.progress.emit(max(75, min(99, 75 + int(pct * 0.24))))
            if pct != last_pct:
                self.log.emit(f"BitLocker encryption progress: {pct}%", "info")
                last_pct = pct
            if data.get("fullyEncrypted") and data.get("protectionOn"):
                self.progress.emit(sequence_progress["complete"])
                self._save_state("SUCCESS", data)
                self.finished_state.emit("success", "BitLocker is fully encrypted and protection is on.")
                return
            if not self._interruptible_wait(int(self.config["encryption_poll_seconds"])):
                return

        self.finished_state.emit("waiting", "Global monitoring deadline reached before completion.")

    def _log_schedule_actions(self, result: OperationResult) -> None:
        actions = list(result.data.get("actions") or [])
        for action in actions:
            name = str(action.get("name") or "SCCM schedule")
            schedule_id = str(action.get("scheduleId") or "")
            short_id = schedule_id.rstrip("}").split("0")[-1] if schedule_id else ""
            status = str(action.get("status") or "unknown")
            hresult = str(action.get("hresult") or "")
            if status == "success":
                self.log.emit(f"{name}: completed.", "success")
            elif status == "skipped":
                suffix = f" ({hresult})" if hresult else ""
                self.log.emit(f"{name}: skipped because this SCCM client does not register the optional schedule{suffix}.", "warning")
            else:
                error = str(action.get("error") or "Unknown TriggerSchedule failure")
                suffix = f" [{hresult}]" if hresult else ""
                self.log.emit(f"{name}: failed{suffix} — {error}", "error")

    def _execute(self, operation: str, timeout: int) -> OperationResult:
        self._wait_if_paused()
        if self.cancel_event.is_set():
            result = OperationResult(operation, False, "cancelled", "Cancelled by technician.")
            self.result.emit(result)
            return result
        self.log.emit(f"Starting: {operation}", "step")
        parameters: dict[str, Any] | None = None
        if operation == "preflight":
            markers = self.config.get("corporate_dns_markers", ["ocp"])
            if not isinstance(markers, list):
                markers = [str(markers)]
            parameters = {
                "CorporateMarkers": ",".join(str(item) for item in markers if str(item).strip()),
                "MinimumFreeDiskMB": int(self.config.get("minimum_free_disk_mb", 1024)),
            }
        result = self.runner.run_operation(operation, timeout=timeout, parameters=parameters)
        self.result.emit(result)
        level = "ok" if result.success else ("warning" if result.status in {"warning", "waiting"} else "error")
        self.log.emit(result.message, level)
        return result

    def _wait_if_paused(self) -> None:
        while self.pause_event.is_set() and not self.cancel_event.is_set():
            self.stage.emit("PAUSED", "Paused safely before the next operation")
            time.sleep(0.25)

    def _interruptible_wait(self, seconds: int) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.cancel_event.is_set():
                self.finished_state.emit(
                    "cancelled",
                    "Assistant stopped safely. SCCM and BitLocker were not disabled.",
                )
                return False
            self._wait_if_paused()
            time.sleep(0.25)
        return True

    def _stop_requested(self) -> bool:
        if self.cancel_event.is_set():
            self.finished_state.emit(
                "cancelled",
                "Assistant stopped safely. Any Windows operation already started may continue.",
            )
            return True
        self._wait_if_paused()
        return self.cancel_event.is_set()

    def _save_state(self, state: str, data: dict[str, Any] | None = None) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "state": state,
                "workflow": self.workflow,
                "startedAt": self._started_at.isoformat(timespec="seconds"),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
                "data": data or {},
            }
            STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass
