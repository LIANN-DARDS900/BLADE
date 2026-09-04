# Security Model

BLADE interacts with privileged Windows endpoint-management components. Treat it as an administrative operations tool, not a consumer desktop utility.

## Trust boundary

The assistant is designed for **authorized managed Windows endpoints** and assumes the technician has permission to inspect and trigger local ConfigMgr client operations.

The application must not be used to bypass organizational security policy, access BitLocker recovery material, or operate on devices the technician is not authorized to manage.

## Deliberate safety restrictions

The current implementation does not directly invoke commands that enable, disable, suspend, resume, or reconfigure BitLocker. It does not add/remove key protectors and does not automatically reboot the endpoint.

Deep `ccmrepair` is also not automatically executed. If basic remediation and `CcmEval` do not restore the client, the workflow blocks and requires technician review.

## Execution policy

PowerShell is started with a **process-scoped** execution-policy bypass. The application does not alter LocalMachine or CurrentUser execution-policy settings.

## Evidence handling

Runtime inspection can discover data such as:

- computer name
- serial number
- assigned ConfigMgr site
- management point
- network suffixes and IPv4 addresses
- SCCM log fragments
- cached deployment metadata

Do not commit exported reports or runtime evidence to a public repository.

The PowerShell evidence routines include filters intended to avoid recovery-password/key material, but exported evidence should still be reviewed before external sharing.

## Repository hygiene

Never commit:

- BitLocker recovery keys or numerical recovery passwords
- credentials or tokens
- corporate DNS names that are not already approved for disclosure
- private management-point infrastructure details
- endpoint reports/logs from production machines
- private software packages from `ccmcache`
- `.env`, certificates, private keys, or signing material

The project `.gitignore` excludes common runtime and secret-bearing files, but that is not a substitute for review.

## Reporting a security issue

If this repository is made public and a security issue is discovered, contact the repository owner privately rather than publishing sensitive endpoint details in a public GitHub issue.
