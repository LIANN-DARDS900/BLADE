# Validation — v0.6.0-adaptive

## Static validation completed

- Python source compiled successfully.
- Required project files are present.
- PowerShell delimiter/string structural validation passed.
- No executable direct BitLocker modification call was found.
- No automatic reboot call was found.
- Dry-run SCCM log and `ccmcache` evidence operations remain present.
- Adaptive SCCM refresh operation is present.

## Evidence driving the patch

The v0.5 field test on an authorized managed spare laptop showed:

- SCCM client healthy
- ConfigMgr site assignment detected (site identifier omitted from public documentation)
- Management Point detected
- Schedule `021` accepted
- Schedule `022` accepted
- Schedule `071` returned `HRESULT 0x80041002`
- Schedule `121` returned `HRESULT 0x80041002`

v0.6 is designed to classify the two optional not-found results as compatibility skips.

## Not yet validated in this build environment

This environment cannot execute Windows-only integration paths. The following must be tested on an authorized managed spare laptop:

- UAC elevation
- PowerShell 5.1 execution
- `root\\ccm` CIM access
- Adaptive schedule classification in the packaged EXE
- SCCM policy delivery
- BitLocker policy arrival and encryption monitoring
- Corporate application-control behavior

## First test acceptance criteria

The Activity page should report approximately:

```text
Machine Policy Assignments Request (021): completed.
Machine Policy Evaluation (022): completed.
Compliance Settings Evaluation (071): skipped ... (0x80041002).
Application Deployment Evaluation (121): skipped ... (0x80041002).
Focused SCCM sync: 2 succeeded, 2 skipped, 0 failed.
```

The workflow must continue to computer Group Policy and policy monitoring after those optional skips.
