# Troubleshooting

## `CLIENT_NOT_INSTALLED`

The ConfigMgr client executable/service could not be found.

Check the enterprise software-distribution process or reinstall/repair the ConfigMgr client using the approved organizational procedure. The assistant does not bootstrap a missing enterprise client.

## `CcmExec` exists but is not running

The basic remediation path can attempt safe client/service recovery. Re-run SCCM Health afterward.

If the service repeatedly stops, investigate the ConfigMgr client logs and Windows event logs instead of repeatedly triggering deployment.

## `root\\ccm` or `SMS_Client` unavailable

This can indicate WMI/ConfigMgr client corruption or an incomplete client installation.

Because the tool depends on `SMS_Client.TriggerSchedule`, this is a blocking condition for policy acceleration.

## `TriggerSchedule` unavailable

If the `SMS_Client` class exists but does not expose the method expected by the tool, treat the client as incompatible/unhealthy for this workflow and investigate the ConfigMgr installation.

## `0x80041002` on schedule `071` or `121`

In v0.6 these schedules are optional. The exact WMI/CIM not-found result is classified as unsupported and skipped.

Do **not** generalize that exception to other errors.

## `0x80041002` on mandatory machine-policy schedules

`021` and `022` are required by the focused path. A missing mandatory schedule should block the workflow and be investigated.

## Access denied / permission error

Confirm the application is running elevated and that the technician account is authorized for local administrative actions.

An access-denied result is not an optional compatibility skip.

## No assigned ConfigMgr site

The assistant reads the local ConfigMgr site assignment. If none is present, verify that the client is correctly assigned and able to reach its management infrastructure.

## Management Point is `N/A`

This may indicate a location-services/client communication issue. Review ConfigMgr client connectivity before forcing repeated policy cycles.

## Corporate-network evidence unconfirmed

The assistant can use configured markers plus site/client evidence to judge whether the device is probably on the intended managed network.

If evidence is unconfirmed, manually verify the endpoint/network before running mutation-capable workflows.

## TPM not ready

BitLocker policy deployment should not be forced through a TPM readiness problem. Resolve TPM/firmware/ownership state according to enterprise policy.

## Pending reboot detected

A reboot can prevent policy or client changes from becoming reliable. The assistant does not automatically reboot the device. Decide explicitly whether to reboot using the approved maintenance process.

## Policy does not arrive before timeout

The workflow can perform limited focused retries. If evidence still does not appear, it collects SCCM log/cache evidence and returns a waiting state.

Investigate:

- policy assignment
- client policy logs
- ConfigMgr boundary/site communication
- Group Policy
- collection membership / deployment targeting
- compliance or application policy dependencies

## Encryption starts but remains incomplete

At that point the assistant is primarily monitoring BitLocker. Check power, storage health, BitLocker status, and enterprise policy rather than repeatedly triggering SCCM actions.
