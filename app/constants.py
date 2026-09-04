from __future__ import annotations

from pathlib import Path
import json
import os
import sys

APP_NAME = "BLADE"
APP_VERSION = "0.6.0-adaptive"
APP_AUTHOR = "Ilyas Nazih"


def resource_path(relative: str) -> Path:
    """Resolve files both in source mode and in a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


CONFIG_PATH = resource_path("config.json")
POWERSHELL_SCRIPT = resource_path("scripts/blade_operations.ps1")
ICON_PATH = resource_path("assets/bitlocker_assistant.ico")

PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
DATA_DIR = PROGRAM_DATA / "BLADE"
LOG_DIR = DATA_DIR / "Logs"
STATE_PATH = DATA_DIR / "state.json"


def load_config() -> dict:
    defaults = {
        "application_name": APP_NAME,
        "policy_wait_seconds": 1800,
        "encryption_poll_seconds": 30,
        "policy_poll_seconds": 20,
        "policy_retry_seconds": [300, 900],
        "max_policy_attempts": 3,
        "global_timeout_hours": 8,
        "minimum_free_disk_mb": 1024,
        "corporate_dns_markers": ["ocp"],
        "fast_sync_actions": ["021", "022", "071", "121"],
        "adaptive_full_sync": True,
        "allow_automatic_ccmrepair": False,
        "allow_automatic_reboot": False,
        "require_action_confirmation": True,
        "enable_ccmcache_discovery": True,
        "enable_sccm_log_evidence": True,
    }
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            defaults.update(json.load(handle))
    except (OSError, ValueError):
        pass
    return defaults
