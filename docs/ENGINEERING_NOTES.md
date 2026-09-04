# Engineering Notes — From Fixed Refresh to Adaptive SCCM

## The original assumption

The earlier workflow treated a fixed set of ConfigMgr `TriggerSchedule` calls as universally available.

That is attractive in development because the sequence is simple: trigger each action, fail if any call fails, then continue to Group Policy and BitLocker monitoring.

The assumption did not survive field testing.

## Field evidence

A managed spare endpoint reported a healthy ConfigMgr client and accepted:

- `021` — Machine Policy Assignments Request
- `022` — Machine Policy Evaluation

The same endpoint returned:

```text
HRESULT 0x80041002
WBEM_E_NOT_FOUND
```

for:

- `071` — Compliance Settings Evaluation
- `121` — Application Deployment Evaluation

Treating this as a globally broken SCCM client caused a false-negative deployment block.

## The v0.6 decision

The new engine gives every schedule a policy classification:

- **Mandatory** schedules are required for the focused machine-policy path.
- **Optional** schedules enrich the refresh but are not assumed to exist on every client.

For optional schedules only, the exact CIM/WMI not-found result is converted from `failed` to `skipped`.

Other failures remain failures.

This matters because these cases are not equivalent:

```text
Optional schedule does not exist on this client  !=  WMI is broken
Optional schedule does not exist on this client  !=  access denied
Optional schedule does not exist on this client  !=  CcmExec unhealthy
Optional schedule does not exist on this client  !=  mandatory machine policy failed
```

## Result model

Each schedule returns an independent status instead of being hidden behind one aggregate success boolean:

```text
success
skipped
failed
```

The UI can therefore show approximately:

```text
Machine Policy Assignments Request (021): completed.
Machine Policy Evaluation (022): completed.
Compliance Settings Evaluation (071): skipped — unsupported (0x80041002).
Application Deployment Evaluation (121): skipped — unsupported (0x80041002).
Focused SCCM sync: 2 succeeded, 2 skipped, 0 failed.
```

## Why this is safer

A naive fix would be to ignore every ConfigMgr trigger error and continue. That would make the workflow appear successful even when policy delivery is genuinely broken.

v0.6 instead narrows the compatibility exception to a known, explicit condition.

The general engineering pattern is:

> Be tolerant of known platform variance, but strict about unknown failure.

## Additional design changes

The adaptive release also reinforces several boundaries:

- focused deployment before broad refresh
- no automatic deep `ccmrepair`
- no automatic reboot
- no direct BitLocker modification
- read-only evidence mode
- controlled policy retries instead of continuous triggering
- evidence collection when policy does not arrive before the deadline

## What remains environment-dependent

Static validation can prove source structure and prohibited-call absence, but it cannot simulate a real ConfigMgr client. Integration acceptance still requires an authorized Windows endpoint with the relevant management stack.
