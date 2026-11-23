$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\install.ps1') -DefinitionsOnly

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Assert-Equal($Expected, $Actual, [string]$Message) {
    if (($Expected -join "`n") -cne ($Actual -join "`n")) {
        throw ($Message + "`nExpected: " + ($Expected -join ', ') + "`nActual: " + ($Actual -join ', '))
    }
}

$script:FixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('ttools installer tests ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $script:FixtureRoot -Force | Out-Null
$script:PythonVersions = @{}
$script:MockResults = @{}
$script:NativeCalls = New-Object 'System.Collections.Generic.List[object]'
$script:FixturePython = Join-Path $script:FixtureRoot 'python.exe'
$script:FixturePythonWrong = Join-Path $script:FixtureRoot 'python313.exe'
$script:FixtureLauncher = Join-Path $script:FixtureRoot 'py.exe'
$script:FixtureWinget = Join-Path $script:FixtureRoot 'winget.exe'
foreach ($path in @($script:FixturePython,$script:FixturePythonWrong,$script:FixtureLauncher,$script:FixtureWinget)) {
    Set-Content -LiteralPath $path -Value 'mock executable' -Encoding ASCII
}
$script:PythonVersions[$script:FixturePython] = '3.14'
$script:PythonVersions[$script:FixturePythonWrong] = '3.13'
$script:AppInstallerFixture = [pscustomobject]@{
    CurrentUserPresent = $false; AnyUserPresent = $false; QuerySucceeded = $true; Locations = @()
}

function script:Invoke-NativeCommand([string]$Executable, [string[]]$Arguments, [int]$TimeoutMilliseconds = 30000) {
    $script:NativeCalls.Add([pscustomobject]@{ Executable = $Executable; Arguments = @($Arguments) })
    if ($script:MockResults.ContainsKey($Executable)) { return $script:MockResults[$Executable] }
    if ($script:PythonVersions.ContainsKey($Executable)) {
        return [pscustomobject]@{ ExitCode = 0; StdOut = $script:PythonVersions[$Executable] + "`n"; StdErr = '' }
    }
    if ($Executable -eq $script:FixtureLauncher -and $Arguments[0] -eq 'list') {
        return [pscustomobject]@{ ExitCode = 0; StdOut = $script:FixturePython + "`n"; StdErr = '' }
    }
    return [pscustomobject]@{ ExitCode = 0; StdOut = 'v1.12.0'; StdErr = '' }
}

function script:Get-AppInstallerPackages { return $script:AppInstallerFixture }

function script:Invoke-WingetPythonInstall([string]$WingetPath) {
    $script:WingetInstallCalls++
    return $script:WingetInstallExitCode
}

function script:Install-OfficialPython314 { $script:OfficialInstallCalls++ }

try {
    Assert-True (Test-Python314 $script:FixturePython) 'A PATH executable reporting CPython 3.14 was rejected.'
    Assert-True (-not (Test-Python314 $script:FixturePythonWrong)) 'Python 3.13 was accepted as Python 3.14.'

    $oldPath = $env:PATH
    $env:PATH = $script:FixtureRoot + ';' + $oldPath
    try {
        $pathPython = Get-Python314
        Assert-Equal $script:FixturePython $pathPython 'Python 3.14 executable on PATH was not discovered.'
    } finally { $env:PATH = $oldPath }

    $withoutLauncher = Get-Python314 -CandidatePaths @($script:FixturePython) -SkipSystemDiscovery
    Assert-Equal $script:FixturePython $withoutLauncher 'Python 3.14 installed without py was not discovered.'

    $launcherPython = Get-Python314 -LauncherPaths @($script:FixtureLauncher) -SkipSystemDiscovery
    Assert-Equal $script:FixturePython $launcherPython 'The Python Launcher did not locate its installed 3.14 runtime.'

    $pathAlias = Join-Path $script:FixtureRoot 'Microsoft\WindowsApps\python.exe'
    New-Item -ItemType Directory -Path (Split-Path -Parent $pathAlias) -Force | Out-Null
    Set-Content -LiteralPath $pathAlias -Value 'mock alias' -Encoding ASCII
    Assert-Equal $null (Get-Python314 -CandidatePaths @($pathAlias) -SkipSystemDiscovery) 'A Microsoft Store execution alias was mistaken for Python.'

    $script:AppInstallerFixture = [pscustomobject]@{
        CurrentUserPresent = $false; AnyUserPresent = $false; QuerySucceeded = $true; Locations = @()
    }
    $oldPath = $env:PATH
    $env:PATH = $script:FixtureRoot + ';' + $oldPath
    try { $pathStatus = Get-WingetStatus }
    finally { $env:PATH = $oldPath }
    Assert-True $pathStatus.Available 'WinGet executable found on PATH was not recognized.'
    Assert-Equal $script:FixtureWinget $pathStatus.Executable 'Wrong PATH WinGet executable was selected.'

    $oldLocalAppData = $env:LOCALAPPDATA
    $oldPath = $env:PATH
    $env:LOCALAPPDATA = $script:FixtureRoot
    $env:PATH = ''
    try {
        $alias = Join-Path $script:FixtureRoot 'Microsoft\WindowsApps\winget.exe'
        New-Item -ItemType Directory -Path (Split-Path -Parent $alias) -Force | Out-Null
        Set-Content -LiteralPath $alias -Value 'mock alias' -Encoding ASCII
        $aliasStatus = Get-WingetStatus
        Assert-True $aliasStatus.Available 'The WindowsApps WinGet alias was not checked.'
        Assert-Equal $alias $aliasStatus.Executable 'The WindowsApps alias path was not used.'
    } finally { $env:LOCALAPPDATA = $oldLocalAppData; $env:PATH = $oldPath }

    $script:AppInstallerFixture = [pscustomobject]@{
        CurrentUserPresent = $true; AnyUserPresent = $true; QuerySucceeded = $true; Locations = @()
    }
    $unlaunchable = Get-WingetStatus -SkipSystemDiscovery
    Assert-True (-not $unlaunchable.Available) 'A missing WinGet alias was reported as launchable.'
    Assert-True $unlaunchable.Installed 'Installed App Installer was reported missing.'
    Assert-True ($unlaunchable.Diagnostic -match 'registered for this user') 'Unavailable current-user App Installer was not diagnosed.'

    $script:AppInstallerFixture = [pscustomobject]@{
        CurrentUserPresent = $false; AnyUserPresent = $true; QuerySucceeded = $true; Locations = @()
    }
    $unregistered = Get-WingetStatus -SkipSystemDiscovery
    Assert-True $unregistered.Installed 'App Installer registered for another user was reported missing.'
    Assert-True ($unregistered.Diagnostic -match 'not registered for this user') 'Unregistered App Installer was not diagnosed.'

    $script:WingetInstallCalls = 0
    $script:OfficialInstallCalls = 0
    $script:WingetInstallExitCode = 0
    $script:PythonSequence = New-Object 'System.Collections.Generic.Queue[string]'
    function script:Get-Python314 { if ($script:PythonSequence.Count -gt 0) { return $script:PythonSequence.Dequeue() }; return $null }
    $script:WingetDetectionCalls = 0
    function script:Get-WingetStatus { $script:WingetDetectionCalls++; return [pscustomobject]@{ Available = $true; Executable = $script:FixtureWinget; Diagnostic = '' } }
    $script:PythonSequence.Enqueue($script:FixturePython)
    Assert-Equal $script:FixturePython (Get-OrInstallPython314) 'Existing Python 3.14 was not returned directly.'
    Assert-Equal 0 $script:WingetDetectionCalls 'WinGet was required although Python 3.14 was already installed.'
    $script:PythonSequence = New-Object 'System.Collections.Generic.Queue[string]'
    $script:PythonSequence.Enqueue($null)
    $script:PythonSequence.Enqueue($script:FixturePython)
    Assert-Equal $script:FixturePython (Get-OrInstallPython314) 'Python was not rediscovered after WinGet installation.'
    Assert-Equal 1 $script:WingetInstallCalls 'The WinGet installation path was not attempted.'
    Assert-Equal 0 $script:OfficialInstallCalls 'The official fallback ran despite a successful WinGet install.'

    $script:WingetInstallCalls = 0
    $script:OfficialInstallCalls = 0
    $script:PythonSequence = New-Object 'System.Collections.Generic.Queue[string]'
    $script:PythonSequence.Enqueue($null)
    $script:PythonSequence.Enqueue($script:FixturePython)
    function script:Get-WingetStatus { return [pscustomobject]@{ Available = $false; Executable = $null; Diagnostic = 'WinGet unavailable fixture.' } }
    Assert-Equal $script:FixturePython (Get-OrInstallPython314) 'Python.org installation was not rediscovered.'
    Assert-Equal 0 $script:WingetInstallCalls 'WinGet was called despite being unavailable.'
    Assert-Equal 1 $script:OfficialInstallCalls 'The verified Python.org fallback was not attempted.'

    $script:AllowPartial = $true
    $script:Preview = $true
    $script:Prefix = 'C:\Users\Тест\TTools Suite'
    $script:Components = 'tthings'
    Assert-Equal @('--allow-partial','--preview','--prefix',$script:Prefix,'--components','tthings') (Get-InstallerArguments) 'Installer flags or Unicode Prefix were not forwarded.'
    $script:AllowPartial = $false
    $script:Preview = $false
    $script:Prefix = $null
    $script:Components = $null
    Assert-Equal @('--allow-partial') (Get-InstallerArguments) 'A default Windows install did not select the supported partial suite.'
    $script:DeferSystem = $true
    Assert-Equal @('--allow-partial','--defer-system') (Get-InstallerArguments) 'The deferred system setup option was not forwarded.'
    $script:DeferSystem = $false

    $standard = Join-Path $script:FixtureRoot 'Programs\Python\Python314\python.exe'
    New-Item -ItemType Directory -Path (Split-Path -Parent $standard) -Force | Out-Null
    Set-Content -LiteralPath $standard -Value 'mock executable' -Encoding ASCII
    $oldLocalAppData = $env:LOCALAPPDATA
    $oldPath = $env:PATH
    $env:LOCALAPPDATA = $script:FixtureRoot
    $env:PATH = ''
    try {
        $standardPaths = Get-StandardPythonPaths
        Assert-True ($standardPaths -contains $standard) 'The standard current-user Python install path was not enumerated.'
    } finally { $env:LOCALAPPDATA = $oldLocalAppData; $env:PATH = $oldPath }

    Write-Host 'Windows installer discovery tests passed.'
} finally {
    Remove-Item -LiteralPath $script:FixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}
