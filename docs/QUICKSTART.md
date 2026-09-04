# BLADE Quick Start

BLADE is a Windows endpoint operations tool for BitLocker readiness, ConfigMgr/SCCM policy orchestration, evidence collection, and encryption monitoring.

## Requirements

- Windows 10 or Windows 11 x64
- Administrator rights for deployment operations
- PowerShell 5.1 or later
- Microsoft Configuration Manager / SCCM client for managed-policy operations
- Python 3.11+ only when running from source

## Run from source

```powershell
git clone https://github.com/LIANN-DARDS900/BLADE.git
cd BLADE
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\START_DEV.bat
```

## Recommended first run

1. Launch BLADE as Administrator.
2. Run **Pre-flight** to inspect readiness without changing the endpoint.
3. Run **Dry run / evidence only** to inspect SCCM, policy, cache, logs, and BitLocker evidence.
4. Review warnings and readiness blockers.
5. On an authorized managed endpoint, use **Fast Deployment** to request the focused policy path.
6. Monitor policy evidence and BitLocker progress from the dashboard.

## Build the Windows executable

```powershell
.\BUILD_SINGLE_EXE.bat
```

See [BUILD.md](BUILD.md) for packaging details and [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) for the full technician workflow.

## Safety boundary

BLADE does not directly enable/disable BitLocker or manipulate protectors. It accelerates and diagnoses the enterprise policy delivery path. Use only on endpoints you are authorized to administer.
