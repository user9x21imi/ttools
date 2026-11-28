param([switch]$InstallVerifiedPythonFallback)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\install.ps1') -DefinitionsOnly

$status = Get-WingetStatus
if ($status.Available) {
    Write-Host ("[PHYSICAL PASS] WinGet launched: " + $status.Executable)
    $savedPath = $env:PATH
    try {
        $remove = @()
        if ($env:LOCALAPPDATA) { $remove += (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps') }
        if ($status.Executable) { $remove += (Split-Path -Parent $status.Executable) }
        $env:PATH = (($savedPath -split ';' | Where-Object {
            $entry = $_.Trim().Trim('"')
            -not ($remove | Where-Object { [string]::Equals($entry, $_, [StringComparison]::OrdinalIgnoreCase) })
        }) -join ';')
        $command = Get-Command 'winget.exe','winget' -CommandType Application -All -ErrorAction SilentlyContinue
        if (-not $command) {
            $hiddenPathStatus = Get-WingetStatus
            if (-not $hiddenPathStatus.Available) {
                throw ('WinGet was installed and launchable before PATH masking, but failed detection after PATH masking: ' + $hiddenPathStatus.Diagnostic)
            }
            Write-Host ("[PHYSICAL PASS] WinGet launched after Get-Command/PATH lookup was removed: " + $hiddenPathStatus.Executable)
        } else {
            Write-Host '[NOT TESTED] Could not fully hide every WinGet executable path from Get-Command on this runner.'
        }
    } finally { $env:PATH = $savedPath }
} else {
    Write-Host ("[NOT TESTED] This Windows runner has no launchable WinGet: " + $status.Diagnostic)
}

$existingPython = Get-Python314
if ($existingPython) {
    if (-not (Test-Python314 $existingPython)) { throw 'Get-Python314 returned an interpreter that failed its real CPython 3.14 probe.' }
    $selectedPython = Get-OrInstallPython314
    if ($selectedPython -ne $existingPython) { throw 'An existing Python 3.14 was not selected directly.' }
    Write-Host ("[PHYSICAL PASS] Existing Python 3.14 selected without dependency installation: " + $selectedPython)
} else {
    Write-Host '[NOT TESTED] No preinstalled Python 3.14 was present on this runner.'
}

if ($InstallVerifiedPythonFallback) {
    $script:FallbackTarget = Join-Path $env:RUNNER_TEMP 'TTools Python fallback с пробелами'
    $script:FallbackPython = Join-Path $script:FallbackTarget 'python.exe'
    $script:FallbackLookups = 0
    $script:RealPythonInstaller = (Get-Command Install-OfficialPython314 -CommandType Function).ScriptBlock

    function script:Get-Python314 {
        $script:FallbackLookups++
        if ($script:FallbackLookups -eq 1) { return $null }
        return $script:FallbackPython
    }
    function script:Get-WingetStatus {
        return [pscustomobject]@{ Available = $false; Executable = $null; Diagnostic = 'Test state: no usable WinGet; exercising the real Python.org fallback installer.' }
    }
    function script:Install-OfficialPython314([string]$TargetDirectory) {
        & $script:RealPythonInstaller $script:FallbackTarget
    }

    try {
        $fallbackPython = Get-OrInstallPython314
        if ($fallbackPython -ne $script:FallbackPython) { throw ('Fallback selected an unexpected interpreter path: ' + $fallbackPython) }
        if (-not (Test-Python314 $fallbackPython)) { throw 'The installed Python.org fallback failed its real CPython 3.14 probe.' }
        Write-Host ("[PHYSICAL PASS] SHA-256/AuthentiCode-verified Python.org fallback installed and ran: " + $fallbackPython)
    } finally {
        Remove-Item -LiteralPath $script:FallbackTarget -Recurse -Force -ErrorAction SilentlyContinue
    }
}
