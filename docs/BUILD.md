# Build Guide

## Development prerequisites

Recommended:

- Windows 10/11 x64
- Windows PowerShell 5.1 or newer
- Python 3.11+
- `pip`

The Python dependencies are intentionally small:

```text
PySide6
PyInstaller
```

## Create the environment

From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Check the workstation

```powershell
.\CHECK_ENV.bat
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_environment.ps1
```

## Static validation

Before building:

```powershell
python .\scripts\static_validate.py
```

Do not ship a build if the static validation fails.

## Run from source

```powershell
.\START_DEV.bat
```

For Windows integration paths, run from an elevated terminal on an authorized test machine.

## Build

Standard build:

```powershell
.\BUILD_EXE.bat
```

Single-file build helper:

```powershell
.\BUILD_SINGLE_EXE.bat
```

The build script includes the required application assets and PowerShell operations layer in the PyInstaller bundle.

## Deployment output

Depending on the chosen PyInstaller mode, the output is produced below `dist\`.

For folder-mode deployments, copy the **entire generated directory**, not only the executable, because PyInstaller runtime dependencies may be stored under `_internal`.

The managed target endpoint does not need a separate Python installation when using the packaged build.

## Release checklist

Before distributing a build internally:

- static validation passes
- source version matches release notes
- test on Windows PowerShell 5.1
- verify UAC elevation behavior
- verify `root\\ccm` access on an authorized ConfigMgr client
- run Dry Run first
- confirm no exported endpoint reports are bundled
- inspect `config.json` for environment-specific values
- antivirus/application-control validation where required
- sign the executable if an approved signing process exists
