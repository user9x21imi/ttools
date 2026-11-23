param()
$ErrorActionPreference = 'Stop'

# Source the installer's real, read-only discovery helpers. DefinitionsOnly
# prevents this diagnostic from installing Python or TTools.
. (Join-Path $PSScriptRoot '..\install.ps1') -DefinitionsOnly

function Test-SamePath([string]$Left, [string]$Right) {
    if (-not $Left -or -not $Right) { return $false }
    try {
        return [string]::Equals([IO.Path]::GetFullPath($Left), [IO.Path]::GetFullPath($Right), [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return [string]::Equals($Left, $Right, [StringComparison]::OrdinalIgnoreCase)
    }
}

function Protect-Path([string]$Path) {
    if (-not $Path) { return '(not reported)' }
    $safe = $Path
    foreach ($entry in @(
        [pscustomobject]@{ Root = $env:LOCALAPPDATA; Token = '<LOCALAPPDATA>' },
        [pscustomobject]@{ Root = $env:APPDATA; Token = '<APPDATA>' },
        [pscustomobject]@{ Root = $env:USERPROFILE; Token = '<USERPROFILE>' }
    )) {
        if ($entry.Root) {
            $safe = [regex]::Replace($safe, [regex]::Escape([string]$entry.Root), [string]$entry.Token, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        }
    }
    return $safe
}

function Get-PythonDiscoveryMethod([string]$Executable) {
    foreach ($name in @('python.exe', 'python3.exe', 'python3.14.exe')) {
        try {
            foreach ($command in (Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
                if (Test-SamePath $Executable $command.Source) { return "PATH command ($name)" }
            }
        } catch { }
    }
    foreach ($candidate in (Get-StandardPythonPaths)) {
        if (Test-SamePath $Executable $candidate) { return 'standard Python install location' }
    }
    foreach ($candidate in (Get-PythonRegistryPaths)) {
        if (Test-SamePath $Executable $candidate) { return 'Python registry entry' }
    }
    $launchers = New-Object 'System.Collections.Generic.List[string]'
    try {
        foreach ($command in (Get-Command 'py.exe', 'py' -CommandType Application -All -ErrorAction SilentlyContinue)) {
            Add-CandidatePath $launchers $command.Source
        }
    } catch { }
    if ($env:LOCALAPPDATA) { Add-CandidatePath $launchers (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe') }
    if ($env:WINDIR) { Add-CandidatePath $launchers (Join-Path $env:WINDIR 'py.exe') }
    foreach ($launcher in $launchers) {
        foreach ($candidate in (Get-LauncherPythonPaths $launcher)) {
            if (Test-SamePath $Executable $candidate) { return 'Python Launcher (py)' }
        }
    }
    return 'validated CPython path (source could not be classified)'
}

function Get-WingetDiscoveryMethod($Status, $PackageState, $PathCommands) {
    if (-not $Status.Available) { return 'no launchable executable found' }
    foreach ($location in $PackageState.Locations) {
        foreach ($name in @('winget.exe', 'AppInstallerCLI.exe')) {
            if (Test-SamePath $Status.Executable (Join-Path $location $name)) { return 'App Installer package executable' }
        }
    }
    $alias = $null
    if ($env:LOCALAPPDATA) { $alias = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe' }
    $isAlias = Test-SamePath $Status.Executable $alias
    $isCommand = $false
    foreach ($command in $PathCommands) {
        if (Test-SamePath $Status.Executable $command.Source) { $isCommand = $true; break }
    }
    if ($isAlias -and $isCommand) { return 'PATH command / App Execution Alias' }
    if ($isAlias) { return 'App Execution Alias' }
    if ($isCommand) { return 'PATH command' }
    return 'launchable App Installer or WinGet path'
}

try {
    Write-Host 'TTools dependency diagnostic (read-only; no installation or configuration changes)'
    Write-Host ("PowerShell: {0} ({1})" -f $PSVersionTable.PSVersion, $PSVersionTable.PSEdition)
    Write-Host ("Windows version: {0}" -f [Environment]::OSVersion.Version)

    $python = Get-Python314
    if ($python -and (Test-Python314 $python)) {
        $source = Get-PythonDiscoveryMethod $python
        Write-Host ("Python: PASS — CPython 3.14 verified via {0}" -f $source)
        Write-Host ("Python path: {0}" -f (Protect-Path $python))
    } else {
        Write-Host 'Python: NOT FOUND — no executable passed the CPython 3.14 runtime check.'
    }

    $winget = Get-WingetStatus
    $appInstaller = Get-AppInstallerState
    $commands = @(Get-Command 'winget.exe', 'winget' -CommandType Application -All -ErrorAction SilentlyContinue)
    Write-Host ("Get-Command winget: {0}" -f $(if ($commands.Count) { 'available to this process' } else { 'not available to this process' }))
    Write-Host ("App Installer package: current-user={0}; any-user={1}; state-query-succeeded={2}" -f $appInstaller.CurrentUserPresent, $appInstaller.AnyUserPresent, $appInstaller.QuerySucceeded)
    if ($winget.Available) {
        $version = Invoke-NativeCommand $winget.Executable @('--version') 10000
        $source = Get-WingetDiscoveryMethod $winget $appInstaller $commands
        Write-Host ("WinGet: PASS — launched via {0}; version={1}" -f $source, $version.StdOut.Trim())
        Write-Host ("WinGet path: {0}" -f (Protect-Path $winget.Executable))
    } else {
        Write-Host ("WinGet: UNAVAILABLE — {0}" -f $winget.Diagnostic)
    }
    Write-Host 'Diagnostic complete. No packages, services, registry settings, PATH entries, or TTools files were changed.'
} catch {
    throw ("Diagnostic failed ({0}). No installation was attempted." -f $_.Exception.GetType().Name)
}
