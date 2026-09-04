# Changelog

## 0.6.0-adaptive

### Engine

- Added `adaptive_sync` PowerShell operation.
- Added per-schedule status: `success`, `skipped`, or `failed`.
- Added HRESULT extraction for CIM exceptions.
- Treats optional `TriggerSchedule` result `0x80041002` as unsupported and safely skips it.
- Keeps `021` and `022` mandatory.
- Preserves all other errors as blocking failures.
- Logs every SCCM schedule result separately in Activity.
- Fast deployment is now adaptive for optional `071` and `121`.
- Full mode renamed to Adaptive SCCM Refresh.

### Interface

- Removed the OCP sidebar logo.
- Replaced blue/cyan decorative styling with a neutral black/gray palette.
- Increased card and control corner radii.
- Added a neutral shield/lock icon.
- Removed the handwritten signature font.
- Rebuilt the About engineering-credit section to avoid duplicate/ghost rendering.
- Updated HTML reports to the neutral design.

### Safety

- No direct BitLocker operation added.
- No automatic reboot added.
- No automatic deep `ccmrepair` added.
- Adaptive refresh confirmation now warns about broader inventory/update workloads.
