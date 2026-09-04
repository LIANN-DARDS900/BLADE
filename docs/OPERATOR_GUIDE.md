# Operator Guide

## Intended operator

IT field/support or endpoint-management technician working on an **authorized Windows workstation** managed through Microsoft Configuration Manager / SCCM.

## Before opening the application

1. Confirm you are authorized to work on the endpoint.
2. Connect the AC adapter.
3. Prefer a physical corporate Ethernet connection.
4. Close unnecessary installers or Windows maintenance tasks.
5. If the device is awaiting a mandatory reboot, decide whether that reboot should happen before deployment.

## Step 1 — Launch as Administrator

Administrative access is required for the full SCCM/Windows inspection and remediation path.

## Step 2 — Run Dry Run / Evidence Only

Dry Run is the safest first action. It does **not** start repair, SCCM trigger actions, `gpupdate`, reboot, or direct BitLocker changes.

Review:

- Ethernet / corporate context
- TPM status
- AC power
- free disk space
- pending reboot state
- SCCM health
- site assignment / management-point visibility
- BitLocker state
- SCCM log/cache evidence

## Step 3 — Resolve blocking readiness issues

Examples:

- reconnect Ethernet
- connect power
- resolve TPM readiness
- complete a required reboot
- repair a missing/broken ConfigMgr client through approved enterprise procedures

Do not treat a warning as equivalent to a failure. The UI distinguishes readiness, warning and blocked states.

## Step 4 — Fast Deployment

Fast Deployment is the preferred acceleration path.

Expected stages:

```text
PREFLIGHT
SCCM_HEALTH
POLICY_SYNC
GROUP_POLICY
POLICY_WAIT
BITLOCKER_MONITOR
```

The focused SCCM path requires the machine policy schedules and can skip specific optional schedules only when the client reports the known unsupported-schedule error.

## Step 5 — Observe policy evidence

Once the policy triggers complete, the assistant waits for BitLocker policy or encryption evidence.

It does not continuously hammer the ConfigMgr client. Focused policy retries are limited by configuration.

If the policy window expires, the workflow returns a waiting state and collects diagnostic evidence instead of pretending the deployment succeeded.

## Step 6 — Monitor encryption

When policy/encryption evidence appears, the assistant switches to BitLocker status monitoring.

Completion requires both:

- volume fully encrypted
- BitLocker protection on

## Step 7 — Export evidence

Use the Activity/report export for troubleshooting or change documentation.

Before sharing a report outside the authorized support context, review it for hostnames, site information, management points, network information, and other corporate metadata.

## When to use Adaptive SCCM Refresh

Use the broader refresh only when:

- Fast Deployment was insufficient
- the endpoint is a controlled test/support device
- broader inventory/update/application evaluation work is acceptable

The broader mode can cause more ConfigMgr activity and should not be the default first action.

## Pause and cancel semantics

Pause stops **new** operations from starting at a safe boundary. It does not freeze an already-running Windows process.

Cancel similarly stops the workflow safely after the current operation boundary. Windows work already initiated may finish independently.
