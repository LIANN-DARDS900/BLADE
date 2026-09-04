function Resolve-ProjectPython {
    [CmdletBinding()]
    param()

    foreach ($candidate in @('py', 'python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }

        try {
            $output = & $candidate -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) {
                return $candidate
            }
        } catch {
            # Continue to the next candidate. This also ignores the Windows Store alias.
        }
    }

    throw @"
A real Python installation was not found.

The WindowsApps python.exe entry is only a Microsoft Store alias and cannot build this project.
Install Python on the development PC, close and reopen the terminal, then verify:

    python --version
    py --version

After that, run START_DEV.bat again.
"@
}
