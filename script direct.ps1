# =============================================================================
#  OCP GROUP IT — BitLocker Auto-Deployment Agent  v3.0
#  Full visible console — nothing runs silently
#  Run as Administrator
# =============================================================================
#Requires -RunAsAdministrator

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
$Config = @{
    ScriptName         = "OCP_BitLocker_AutoDeploy"
    ScriptPath         = $MyInvocation.MyCommand.Path
    LogDir             = "C:\OCP_Logs"
    LogFile            = "C:\OCP_Logs\BitLocker_Deploy.log"
    StateFile          = "C:\OCP_Logs\cycle_state.json"
    MaxCycles          = 12
    RebootDelaySec     = 30
    SleepBetweenActSec = 3
    DriveToEncrypt     = "C:"
    TaskTriggerDelay   = "PT2M"
}

$SCCMActions = [ordered]@{
    "Machine Policy Retrieval & Eval"   = "{00000000-0000-0000-0000-000000000021}"
    "Machine Policy Evaluation"         = "{00000000-0000-0000-0000-000000000022}"
    "Hardware Inventory"                = "{00000000-0000-0000-0000-000000000001}"
    "Software Inventory"                = "{00000000-0000-0000-0000-000000000002}"
    "Discovery Data Collection"         = "{00000000-0000-0000-0000-000000000003}"
    "Software Updates Scan"             = "{00000000-0000-0000-0000-000000000113}"
    "Software Updates Deployment Eval"  = "{00000000-0000-0000-0000-000000000108}"
    "Compliance Settings Baseline"      = "{00000000-0000-0000-0000-000000000071}"
    "Application Deployment Evaluation" = "{00000000-0000-0000-0000-000000000121}"
    "Windows Installer Source Update"   = "{00000000-0000-0000-0000-000000000032}"
}

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSOLE WINDOW SETUP
# ═══════════════════════════════════════════════════════════════════════════════

$code = @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]   public static extern bool ShowWindow(IntPtr h, int n);
    public const int SW_MAXIMIZE = 3;
}
"@
Add-Type -TypeDefinition $code -ErrorAction SilentlyContinue
try { [Win32]::ShowWindow([Win32]::GetConsoleWindow(), [Win32]::SW_MAXIMIZE) | Out-Null } catch {}

try {
    $Host.UI.RawUI.BufferSize  = New-Object System.Management.Automation.Host.Size(220, 3000)
    $Host.UI.RawUI.WindowSize  = New-Object System.Management.Automation.Host.Size(130, 50)
    $Host.UI.RawUI.WindowTitle = "OCP GROUP IT  —  BitLocker Auto-Deploy Agent v3.0"
} catch {}

$Host.UI.RawUI.BackgroundColor = "Black"
$Host.UI.RawUI.ForegroundColor = "White"
Clear-Host

# ═══════════════════════════════════════════════════════════════════════════════
#  UI FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

function Write-Banner {
    Write-Host ""
    Write-Host "  ========================================================================" -ForegroundColor Cyan
    Write-Host "  ||  ___  ____ ____     ____ ____ ____ _  _ ___     ___ ___           ||" -ForegroundColor Cyan
    Write-Host "  ||  |  | |    |  |     | __ |__/ |  | |  | |  |     |   |            ||" -ForegroundColor Cyan
    Write-Host "  ||  |__| |___ |__|     |__] |  \ |__| |__| |__|     |   |            ||" -ForegroundColor Cyan
    Write-Host "  ||                                                                    ||" -ForegroundColor Cyan
    Write-Host "  ||         IT Department  -  BitLocker Auto-Deployment Agent v3.0    ||" -ForegroundColor Cyan
    Write-Host "  ========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-SectionHeader {
    param([string]$Title)
    Write-Host ""
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host ("  |  >>> " + $Title.ToUpper().PadRight(68) + "|") -ForegroundColor DarkCyan
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host ""
}

function Write-Log {
    param([string]$m, [string]$Level = "INFO")
    $ts = Get-Date -Format "HH:mm:ss"
    $tag = switch ($Level) {
        "OK"      { " [ OK ]  " }
        "STEP"    { " [STEP]  " }
        "WARN"    { " [WARN]  " }
        "ERROR"   { " [ERROR] " }
        "DONE"    { " [DONE]  " }
        default   { " [INFO]  " }
    }
    $color = switch ($Level) {
        "OK"      { "Green"   }
        "STEP"    { "Magenta" }
        "WARN"    { "Yellow"  }
        "ERROR"   { "Red"     }
        "DONE"    { "Cyan"    }
        default   { "White"   }
    }
    Write-Host "  [$ts]" -NoNewline -ForegroundColor DarkGray
    Write-Host $tag      -NoNewline -ForegroundColor $color
    Write-Host $m                   -ForegroundColor White
    Add-Content $Config.LogFile "[$ts]$tag$m" -ErrorAction SilentlyContinue
}

function Write-Divider {
    Write-Host "  ------------------------------------------------------------------------" -ForegroundColor DarkGray
}

function Write-ProgressBar {
    param([int]$Percent, [int]$Width = 50)
    $filled = [Math]::Round($Percent / 100 * $Width)
    $empty  = $Width - $filled
    $bar    = ("#" * $filled) + ("-" * $empty)
    Write-Host "    [" -NoNewline -ForegroundColor DarkGray
    Write-Host $bar    -NoNewline -ForegroundColor Cyan
    Write-Host "] " -NoNewline -ForegroundColor DarkGray
    Write-Host "$Percent%" -ForegroundColor White
}

function Write-Countdown {
    param([int]$Seconds, [string]$Message = "Continuing in")
    Write-Host ""
    for ($i = $Seconds; $i -gt 0; $i--) {
        Write-Host ("`r  >  $Message ${i}s...   ") -NoNewline -ForegroundColor Yellow
        Start-Sleep -Seconds 1
    }
    Write-Host "`r  >  Done.                              " -ForegroundColor Green
    Write-Host ""
}

function Write-Spinner {
    param([string]$Message, [int]$Seconds)
    $frames = @("|","/" ,"-","\\")
    $end    = (Get-Date).AddSeconds($Seconds)
    $i      = 0
    while ((Get-Date) -lt $end) {
        Write-Host ("`r  $($frames[$i % 4])  $Message...   ") -NoNewline -ForegroundColor Cyan
        Start-Sleep -Milliseconds 150
        $i++
    }
    Write-Host "`r  +  $Message -- Done.                    " -ForegroundColor Green
}

function Write-MachineCard {
    $serial = try { (Get-WmiObject Win32_BIOS).SerialNumber }          catch { "N/A" }
    $model  = try { (Get-WmiObject Win32_ComputerSystem).Model }        catch { "N/A" }
    $os     = try { (Get-WmiObject Win32_OperatingSystem).Caption }     catch { "N/A" }
    $ip     = try { (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" } | Select-Object -First 1).IPAddress } catch { "N/A" }
    $tpmOK  = try { (Get-Tpm).TpmReady } catch { $false }

    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host "  |                    MACHINE INFORMATION                          |" -ForegroundColor DarkCyan
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host "  |  Computer  : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $env:COMPUTERNAME) -NoNewline; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  Serial    : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $serial)           -NoNewline -ForegroundColor Yellow; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  Model     : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $model)            -NoNewline; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  OS        : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $os)               -NoNewline; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  IP        : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $ip)               -NoNewline; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  TPM Ready : " -NoNewline -ForegroundColor DarkCyan
    if ($tpmOK) { Write-Host ("{0,-52}" -f "YES  [OK]") -NoNewline -ForegroundColor Green }
    else        { Write-Host ("{0,-52}" -f "NO   [!!]") -NoNewline -ForegroundColor Red   }
    Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  |  Log File  : " -NoNewline -ForegroundColor DarkCyan; Write-Host ("{0,-52}" -f $Config.LogFile) -NoNewline -ForegroundColor DarkGray; Write-Host "|" -ForegroundColor DarkCyan
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor DarkCyan
    Write-Host ""
}

function Write-BitLockerCard {
    param($s)
    $prot = if ($s) { $s.ProtectionStatus  } else { "UNKNOWN" }
    $vol  = if ($s) { $s.VolumeStatus       } else { "UNKNOWN" }
    $pct  = if ($s) { $s.EncryptionPercent  } else { 0 }
    $keys = if ($s) { $s.KeyProtectors      } else { "N/A" }

    $protColor = if ($prot -eq "On") { "Green" } elseif ($prot -eq "Off") { "Red" } else { "Yellow" }
    $volColor  = if ($vol -eq "FullyEncrypted") { "Green" } elseif ($vol -eq "FullyDecrypted") { "Red" } else { "Yellow" }

    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |                    BITLOCKER STATUS                             |" -ForegroundColor Cyan
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  Drive          : " -NoNewline -ForegroundColor Cyan; Write-Host ("{0,-47}" -f $Config.DriveToEncrypt) -NoNewline; Write-Host "|" -ForegroundColor Cyan
    Write-Host "  |  Protection     : " -NoNewline -ForegroundColor Cyan; Write-Host ("{0,-47}" -f $prot) -NoNewline -ForegroundColor $protColor; Write-Host "|" -ForegroundColor Cyan
    Write-Host "  |  Volume Status  : " -NoNewline -ForegroundColor Cyan; Write-Host ("{0,-47}" -f $vol)  -NoNewline -ForegroundColor $volColor;  Write-Host "|" -ForegroundColor Cyan
    Write-Host "  |  Key Protectors : " -NoNewline -ForegroundColor Cyan; Write-Host ("{0,-47}" -f $keys) -NoNewline;                             Write-Host "|" -ForegroundColor Cyan
    Write-Host "  |  Encryption     :                                               |" -ForegroundColor Cyan
    Write-Host "  |  " -NoNewline -ForegroundColor Cyan
    Write-ProgressBar -Percent $pct -Width 54
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════════════════════
#  STATE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

function Get-State {
    if (Test-Path $Config.StateFile) { return Get-Content $Config.StateFile | ConvertFrom-Json }
    return [PSCustomObject]@{ CycleNumber = 0; StartTime = (Get-Date -Format "o") }
}
function Save-State($s) { $s | ConvertTo-Json | Set-Content $Config.StateFile -Force }

# ═══════════════════════════════════════════════════════════════════════════════
#  CORE ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

function Register-PersistentTask {
    Write-Log "Registering Scheduled Task for reboot persistence..." "STEP"
    Unregister-ScheduledTask -TaskName $Config.ScriptName -Confirm:$false -ErrorAction SilentlyContinue
    $action    = New-ScheduledTaskAction -Execute "powershell.exe" `
                     -Argument "-NonInteractive -NoProfile -ExecutionPolicy Bypass -File `"$($Config.ScriptPath)`""
    $trigger   = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = $Config.TaskTriggerDelay
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
                     -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName $Config.ScriptName `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description "OCP IT - BitLocker auto-deploy agent. Self-removes on completion." -Force | Out-Null
    Write-Log "Scheduled Task '$($Config.ScriptName)' is registered. Script will resume after any reboot." "OK"
}

function Remove-PersistentTask {
    Write-Log "Removing Scheduled Task (no longer needed)..." "STEP"
    Unregister-ScheduledTask -TaskName $Config.ScriptName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log "Scheduled Task removed cleanly." "OK"
}

function Invoke-SCCMActions {
    Write-SectionHeader "SCCM CLIENT ACTIONS"

    $svc = Get-Service -Name CcmExec -ErrorAction SilentlyContinue
    if (-not $svc) { Write-Log "SCCM client (CcmExec) not found - skipping SCCM step." "WARN"; return }
    if ($svc.Status -ne "Running") {
        Write-Log "CcmExec is stopped - attempting to start..." "WARN"
        Start-Service CcmExec -ErrorAction SilentlyContinue
        Write-Spinner "Waiting for CcmExec to start" 10
    }
    Write-Log "SCCM client (CcmExec) is running." "OK"
    Write-Divider

    $total = $SCCMActions.Count
    $idx   = 0
    foreach ($name in $SCCMActions.Keys) {
        $idx++
        $guid = $SCCMActions[$name]
        Write-Host ("  [{0:D2}/{1:D2}] Triggering: " -f $idx, $total) -NoNewline -ForegroundColor DarkGray
        Write-Host $name.PadRight(45) -NoNewline -ForegroundColor Cyan
        try {
            Invoke-WmiMethod -Namespace "root\ccm" -Class "SMS_Client" `
                -Name "TriggerSchedule" -ArgumentList $guid -ErrorAction Stop | Out-Null
            Write-Host " --> OK" -ForegroundColor Green
            Add-Content $Config.LogFile "[$(Get-Date -f HH:mm:ss)] OK   Triggered: $name" -EA SilentlyContinue
        } catch {
            Write-Host " --> FAILED: $_" -ForegroundColor Red
            Add-Content $Config.LogFile "[$(Get-Date -f HH:mm:ss)] WARN Could not trigger: $name - $_" -EA SilentlyContinue
        }
        Start-Sleep -Seconds $Config.SleepBetweenActSec
    }

    Write-Divider
    Write-Spinner "Waiting for SCCM to process all policies" 30
}

function Invoke-GroupPolicyUpdate {
    Write-SectionHeader "GROUP POLICY UPDATE"

    Write-Log "Running: gpupdate /force /wait:60" "STEP"
    Write-Host ""
    $out1 = & gpupdate /force /wait:60 2>&1
    $out1 | ForEach-Object { Write-Host "    |  $_" -ForegroundColor DarkGray }
    Write-Host ""
    Write-Log "gpupdate /force completed." "OK"
    Write-Divider

    Write-Log "Running: gpupdate /target:computer /force /wait:60" "STEP"
    Write-Host ""
    $out2 = & gpupdate /target:computer /force /wait:60 2>&1
    $out2 | ForEach-Object { Write-Host "    |  $_" -ForegroundColor DarkGray }
    Write-Host ""
    Write-Log "gpupdate /target:computer completed." "OK"

    Write-Spinner "Letting policies fully apply" 20
}

function Get-BitLockerStatus {
    try {
        $vol = Get-BitLockerVolume -MountPoint $Config.DriveToEncrypt -ErrorAction Stop
        return [PSCustomObject]@{
            ProtectionStatus  = $vol.ProtectionStatus
            VolumeStatus      = $vol.VolumeStatus
            EncryptionPercent = $vol.EncryptionPercentage
            KeyProtectors     = ($vol.KeyProtector | ForEach-Object { $_.KeyProtectorType }) -join ", "
        }
    } catch {
        Write-Log "Could not read BitLocker volume: $_" "WARN"
        return $null
    }
}

function Test-BitLockerComplete($s) {
    return ($s -and $s.ProtectionStatus -eq "On" -and $s.VolumeStatus -eq "FullyEncrypted")
}

function Invoke-AutoReboot {
    Write-Host ""
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |   REBOOT REQUIRED - BitLocker not yet fully active                    |" -ForegroundColor Yellow
    Write-Host "  |   The script will AUTOMATICALLY resume after the reboot.              |" -ForegroundColor Yellow
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor Yellow
    Write-Countdown -Seconds $Config.RebootDelaySec -Message "Rebooting in"
    Restart-Computer -Force
}

function Write-SuccessBanner {
    $state   = Get-State
    $elapsed = [math]::Round(((Get-Date) - [datetime]$state.StartTime).TotalMinutes, 1)

    Clear-Host
    Write-Host ""
    Write-Host "  ========================================================================" -ForegroundColor Green
    Write-Host "  ||                                                                    ||" -ForegroundColor Green
    Write-Host "  ||          BITLOCKER DEPLOYMENT COMPLETE  --  SUCCESS               ||" -ForegroundColor Green
    Write-Host "  ||                                                                    ||" -ForegroundColor Green
    Write-Host "  ||          Drive C: is FULLY ENCRYPTED and PROTECTED                ||" -ForegroundColor Green
    Write-Host "  ||                                                                    ||" -ForegroundColor Green
    Write-Host "  ========================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor Green
    Write-Host "  |  Computer  : " -NoNewline -ForegroundColor Green; Write-Host ("{0,-52}" -f $env:COMPUTERNAME)      -NoNewline -ForegroundColor White; Write-Host "|" -ForegroundColor Green
    Write-Host "  |  Cycles    : " -NoNewline -ForegroundColor Green; Write-Host ("{0,-52}" -f $state.CycleNumber)     -NoNewline -ForegroundColor White; Write-Host "|" -ForegroundColor Green
    Write-Host "  |  Duration  : " -NoNewline -ForegroundColor Green; Write-Host ("{0,-52}" -f "$elapsed minutes")     -NoNewline -ForegroundColor White; Write-Host "|" -ForegroundColor Green
    Write-Host "  |  Log       : " -NoNewline -ForegroundColor Green; Write-Host ("{0,-52}" -f $Config.LogFile)        -NoNewline -ForegroundColor DarkGray; Write-Host "|" -ForegroundColor Green
    Write-Host "  +------------------------------------------------------------------+" -ForegroundColor Green
    Write-Host ""
    Write-Host "  The laptop is ready to be handed to the user." -ForegroundColor White
    Write-Host ""
    Add-Content $Config.LogFile "[$(Get-Date -f HH:mm:ss)] DONE  Complete. Cycles=$($state.CycleNumber) Duration=${elapsed}min" -EA SilentlyContinue
}

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

New-Item -ItemType Directory -Force -Path $Config.LogDir | Out-Null

Write-Banner
Write-MachineCard

$state = Get-State
$state.CycleNumber++
Save-State $state

Write-SectionHeader "STARTING CYCLE $($state.CycleNumber) of $($Config.MaxCycles) MAXIMUM"
Write-Log "Log file  : $($Config.LogFile)" "INFO"
Write-Log "State file: $($Config.StateFile)" "INFO"
Write-Divider

# 1 - Scheduled Task
Write-SectionHeader "STEP 1 / 4  -  SCHEDULED TASK (REBOOT PERSISTENCE)"
Register-PersistentTask

# 2 - SCCM
Write-SectionHeader "STEP 2 / 4  -  SCCM CLIENT ACTIONS"
Invoke-SCCMActions

# 3 - GPUpdate
Write-SectionHeader "STEP 3 / 4  -  GROUP POLICY UPDATE"
Invoke-GroupPolicyUpdate

# 4 - BitLocker check
Write-SectionHeader "STEP 4 / 4  -  BITLOCKER STATUS CHECK"
Write-Log "Reading BitLocker status on $($Config.DriveToEncrypt)..." "STEP"
$blStatus = Get-BitLockerStatus
Write-BitLockerCard $blStatus

# Decision
if (Test-BitLockerComplete $blStatus) {

    Write-SuccessBanner
    Remove-PersistentTask
    Move-Item $Config.StateFile "$($Config.LogDir)\cycle_state_DONE.json" -Force -EA SilentlyContinue
    Write-Host "  Press any key to close this window..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 0

} elseif ($state.CycleNumber -ge $Config.MaxCycles) {

    Write-Host ""
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor Red
    Write-Host "  |   MAX CYCLES REACHED - Manual investigation required                  |" -ForegroundColor Red
    Write-Host "  +------------------------------------------------------------------------+" -ForegroundColor Red
    Write-Log "Check SCCM BitLocker policy targeting" "ERROR"
    Write-Log "Verify Serial Number is registered in SCCM BitLocker list" "ERROR"
    Write-Log "Check TPM chip is present and enabled in BIOS" "ERROR"
    Write-Log "Verify ethernet cable is connected to OCP network" "ERROR"
    Write-Log "Review full logs at: $($Config.LogFile)" "ERROR"
    Write-Host ""
    Remove-PersistentTask
    Write-Host "  Press any key to close..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1

} else {

    Write-Log "Cycle $($state.CycleNumber) done - BitLocker not yet complete. Rebooting..." "WARN"
    Invoke-AutoReboot

}
