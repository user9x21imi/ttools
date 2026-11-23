param(
    [switch]$AllowPartial,
    [switch]$Preview,
    [string]$Prefix,
    [string]$Components,
    [string]$BootstrapUrl,
    [switch]$LocalPackage,
    [switch]$DeferSystem,
    [switch]$DefinitionsOnly
)

$ErrorActionPreference = 'Stop'
$script:InstallerRoot = $PSScriptRoot
if (-not $script:InstallerRoot) { $script:InstallerRoot = $env:TTOOLS_LOCAL_PACKAGE_ROOT }
if (-not $script:InstallerRoot) { $script:InstallerRoot = (Get-Location).Path }

# Python.org publishes this installer and its digest on the official release page.
# Keep both values together so the fallback remains reproducible and verifiable.
$script:Python314Version = '3.14.10'
$script:Python314InstallerSha256 = '92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965'
$script:Python314InstallerUrl = 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.exe'
$script:BootstrapUrl = 'https://raw.githubusercontent.com/user9x21imi/ttools/main/bootstrap.py'
if ($BootstrapUrl) { $script:BootstrapUrl = $BootstrapUrl }
$script:PythonProbe = 'import sys,venv,ensurepip; print("%d.%d" % sys.version_info[:2])'

function Quote-ProcessArgument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
            [void]$builder.Append('"')
            $slashes = 0
            continue
        }
        if ($slashes -gt 0) { [void]$builder.Append(('\' * $slashes)); $slashes = 0 }
        [void]$builder.Append($character)
    }
    if ($slashes -gt 0) { [void]$builder.Append(('\' * (2 * $slashes))) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Invoke-NativeCommand([string]$Executable, [string[]]$Arguments, [int]$TimeoutMilliseconds = 30000) {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    $start.Arguments = (($Arguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { return [pscustomobject]@{ ExitCode = -1; StdOut = ''; StdErr = 'Process did not start.' } }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            try { $process.Kill() } catch { }
            return [pscustomobject]@{ ExitCode = -1; StdOut = ''; StdErr = 'Timed out.' }
        }
        $process.WaitForExit()
        return [pscustomobject]@{ ExitCode = $process.ExitCode; StdOut = $stdoutTask.Result; StdErr = $stderrTask.Result }
    } catch {
        return [pscustomobject]@{ ExitCode = -1; StdOut = ''; StdErr = $_.Exception.Message }
    } finally {
        $process.Dispose()
    }
}

function Test-Python314([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    # Microsoft Store aliases can exist on PATH without containing Python.
    if ($Executable -match '(?i)\\Microsoft\\WindowsApps\\python(?:3(?:\.14)?)?(?:\.exe)?$') { return $false }
    $result = Invoke-NativeCommand $Executable @('-I', '-c', $script:PythonProbe) 15000
    if ($result.ExitCode -ne 0) { return $false }
    foreach ($line in ($result.StdOut -split "`r?`n")) {
        if ($line.Trim() -eq '3.14') { return $true }
    }
    return $false
}

function Add-CandidatePath([System.Collections.Generic.List[string]]$List, [string]$Path) {
    if (-not $Path) { return }
    $candidate = [Environment]::ExpandEnvironmentVariables($Path.Trim().Trim('"'))
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return }
    if ($candidate -match '(?i)\\Microsoft\\WindowsApps\\python(?:3(?:\.14)?)?(?:\.exe)?$') { return }
    foreach ($existing in $List) {
        if ([string]::Equals($existing, $candidate, [StringComparison]::OrdinalIgnoreCase)) { return }
    }
    $List.Add($candidate)
}

function Get-LauncherPythonPaths([string]$LauncherPath) {
    $paths = New-Object 'System.Collections.Generic.List[string]'
    if (-not $LauncherPath -or -not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)) { return @() }
    $queries = New-Object 'System.Collections.Generic.List[object]'
    $queries.Add([string[]]@('list', '--format=exe', '3.14'))
    $queries.Add([string[]]@('-0p'))
    $queries.Add([string[]]@('--list-paths'))
    foreach ($arguments in $queries) {
        $result = Invoke-NativeCommand $LauncherPath $arguments 15000
        if ($result.ExitCode -ne 0) { continue }
        foreach ($line in ($result.StdOut -split "`r?`n")) {
            $text = $line.Trim()
            if ($text -match '^(?i:[A-Z]:\\.*python(?:3(?:\.14)?)?\.exe)$') {
                Add-CandidatePath $paths $text
                continue
            }
            if ($text -match '(?i)"([A-Z]:\\[^"\r\n]*python(?:3(?:\.14)?)?\.exe)"') {
                Add-CandidatePath $paths $Matches[1]
                continue
            }
            if ($text -match '(?i)([A-Z]:\\.*python(?:3(?:\.14)?)?\.exe)$') {
                Add-CandidatePath $paths $Matches[1]
            }
        }
        if ($paths.Count -gt 0) { break }
    }
    return @($paths.ToArray())
}

function Get-PythonRegistryPaths {
    $result = New-Object 'System.Collections.Generic.List[string]'
    $roots = @(
        'Registry::HKEY_CURRENT_USER\Software\Python\PythonCore\3.14\InstallPath',
        'Registry::HKEY_LOCAL_MACHINE\Software\Python\PythonCore\3.14\InstallPath',
        'Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Python\PythonCore\3.14\InstallPath',
        'Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe',
        'Registry::HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe',
        'Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\python.exe'
    )
    foreach ($root in $roots) {
        try {
            $key = Get-Item -LiteralPath $root -ErrorAction Stop
            if ($root -match '\\InstallPath$') {
                $installPath = $key.GetValue('')
                $exePath = $key.GetValue('ExecutablePath')
                if ($exePath) { Add-CandidatePath $result ([string]$exePath) }
                if ($installPath) { Add-CandidatePath $result (Join-Path ([string]$installPath) 'python.exe') }
            } else {
                $exePath = $key.GetValue('')
                if ($exePath) { Add-CandidatePath $result ([string]$exePath) }
            }
        } catch { }
    }
    return @($result.ToArray())
}

function Get-StandardPythonPaths {
    $known = New-Object 'System.Collections.Generic.List[string]'
    if ($env:LOCALAPPDATA) {
        foreach ($relative in @(
            'Programs\Python\Python314\python.exe',
            'Programs\Python\Python314-64\python.exe',
            'Python\pythoncore-3.14-64\python.exe',
            'Python\pythoncore-3.14-32\python.exe'
        )) {
            $known.Add((Join-Path $env:LOCALAPPDATA $relative))
        }
    }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:USERPROFILE)) {
        if ($base) { $known.Add((Join-Path $base 'Python314\python.exe')) }
    }
    return @($known.ToArray())
}

function Get-Python314([string[]]$CandidatePaths, [string[]]$LauncherPaths, [switch]$SkipSystemDiscovery) {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($path in $CandidatePaths) { Add-CandidatePath $candidates $path }

    if (-not $SkipSystemDiscovery) {
        foreach ($name in @('python.exe', 'python3.exe', 'python3.14.exe')) {
            try {
                foreach ($command in (Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
                    Add-CandidatePath $candidates $command.Source
                }
            } catch { }
        }

        foreach ($path in (Get-StandardPythonPaths)) { Add-CandidatePath $candidates $path }
        foreach ($path in (Get-PythonRegistryPaths)) { Add-CandidatePath $candidates $path }
    }

    $launchers = New-Object 'System.Collections.Generic.List[string]'
    foreach ($path in $LauncherPaths) { Add-CandidatePath $launchers $path }
    if (-not $SkipSystemDiscovery) {
        try {
            foreach ($command in (Get-Command 'py.exe', 'py' -CommandType Application -All -ErrorAction SilentlyContinue)) {
                Add-CandidatePath $launchers $command.Source
            }
        } catch { }
        if ($env:LOCALAPPDATA) { Add-CandidatePath $launchers (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe') }
        if ($env:WINDIR) { Add-CandidatePath $launchers (Join-Path $env:WINDIR 'py.exe') }
    }
    foreach ($launcher in $launchers) {
        foreach ($path in (Get-LauncherPythonPaths $launcher)) { Add-CandidatePath $candidates $path }
    }

    foreach ($candidate in $candidates) {
        if (Test-Python314 $candidate) { return $candidate }
    }
    return $null
}

function Get-AppInstallerState {
    $locations = New-Object 'System.Collections.Generic.List[string]'
    $state = [pscustomobject]@{ CurrentUserPresent = $false; AnyUserPresent = $false; QuerySucceeded = $false; Locations = @() }
    $appx = Get-Command Get-AppxPackage -CommandType Cmdlet -ErrorAction SilentlyContinue
    if ($appx) {
        try {
            $current = @(Get-AppxPackage -Name 'Microsoft.DesktopAppInstaller' -ErrorAction Stop)
            $state.QuerySucceeded = $true
            $state.CurrentUserPresent = $current.Count -gt 0
            foreach ($package in $current) {
                if ($package.InstallLocation) { $locations.Add([string]$package.InstallLocation) }
            }
        } catch { }
        try {
            $all = @(Get-AppxPackage -AllUsers -Name 'Microsoft.DesktopAppInstaller' -ErrorAction Stop)
            if ($all.Count -gt 0) { $state.AnyUserPresent = $true }
            if ($all.Count -gt 0) { $state.QuerySucceeded = $true }
            foreach ($package in $all) {
                if ($package.InstallLocation) { $locations.Add([string]$package.InstallLocation) }
            }
        } catch { }
    }
    if ($state.CurrentUserPresent) { $state.AnyUserPresent = $true }
    try {
        $registered = Get-ChildItem -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications' -ErrorAction Stop
        $state.QuerySucceeded = $true
        foreach ($entry in $registered) {
            if ($entry.PSChildName -like 'Microsoft.DesktopAppInstaller_*') { $state.AnyUserPresent = $true; break }
        }
    } catch { }
    $state.Locations = @($locations.ToArray() | Select-Object -Unique)
    return $state
}

function Get-WingetStatus([string[]]$ExecutablePaths, [string[]]$AliasPaths, [string[]]$PackageLocations, [switch]$SkipSystemDiscovery) {
    $packages = Get-AppInstallerPackages
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($path in $ExecutablePaths) { Add-CandidatePath $candidates $path }
    foreach ($path in $AliasPaths) { Add-CandidatePath $candidates $path }
    foreach ($location in $PackageLocations) {
        if ($location) {
            Add-CandidatePath $candidates (Join-Path $location 'winget.exe')
            Add-CandidatePath $candidates (Join-Path $location 'AppInstallerCLI.exe')
        }
    }
    if ($packages.Locations) {
        foreach ($location in $packages.Locations) {
            if ($location) {
                Add-CandidatePath $candidates (Join-Path $location 'winget.exe')
                Add-CandidatePath $candidates (Join-Path $location 'AppInstallerCLI.exe')
            }
        }
    }

    if (-not $SkipSystemDiscovery) {
        try {
            foreach ($command in (Get-Command 'winget.exe', 'winget' -CommandType Application -All -ErrorAction SilentlyContinue)) {
                Add-CandidatePath $candidates $command.Source
            }
        } catch { }
        if ($env:LOCALAPPDATA) {
            Add-CandidatePath $candidates (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe')
        }
    }

    foreach ($candidate in $candidates) {
        $result = Invoke-NativeCommand $candidate @('--version') 10000
        if ($result.ExitCode -eq 0) {
            return [pscustomobject]@{
                Available = $true; Executable = $candidate; Installed = $packages.AnyUserPresent
                RegisteredForCurrentUser = $packages.CurrentUserPresent; RegistrationKnown = $packages.QuerySucceeded
                Diagnostic = 'WinGet executable launched successfully.'
            }
        }
    }

    if ($packages.AnyUserPresent -and -not $packages.CurrentUserPresent) {
        $diagnostic = 'App Installer is installed for another user or is not registered for this user; no launchable WinGet alias was found. No package registration was changed.'
    } elseif ($packages.CurrentUserPresent) {
        $diagnostic = 'App Installer is registered for this user, but its WinGet executable or alias could not be launched.'
    } elseif (-not $packages.QuerySucceeded) {
        $diagnostic = 'No launchable WinGet executable was found; App Installer package state could not be queried.'
    } else {
        $diagnostic = 'No launchable WinGet executable or App Installer package was found.'
    }
    return [pscustomobject]@{
        Available = $false; Executable = $null; Installed = $packages.AnyUserPresent
        RegisteredForCurrentUser = $packages.CurrentUserPresent; RegistrationKnown = $packages.QuerySucceeded
        Diagnostic = $diagnostic
    }
}

function Get-AppInstallerPackages {
    return Get-AppInstallerState
}

function Invoke-WingetPythonInstall([string]$WingetPath) {
    $args = @('install', '--id', 'Python.Python.3.14', '--exact', '--scope', 'user', '--silent',
              '--accept-package-agreements', '--accept-source-agreements')
    Write-Host 'Installing CPython 3.14 through WinGet...'
    $result = Invoke-NativeCommand $WingetPath $args 900000
    if ($result.StdOut) { Write-Host $result.StdOut.TrimEnd() }
    if ($result.StdErr) { Write-Host $result.StdErr.TrimEnd() }
    return $result.ExitCode
}

function Install-OfficialPython314 {
    $work = Join-Path ([IO.Path]::GetTempPath()) ('ttools-python-' + [guid]::NewGuid().ToString('N'))
    $installer = Join-Path $work 'python-3.14.10-amd64.exe'
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    try {
        Write-Host 'Downloading the verified CPython installer from python.org...'
        Invoke-WebRequest -UseBasicParsing -Uri $script:Python314InstallerUrl -OutFile $installer -ErrorAction Stop
        $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $script:Python314InstallerSha256) { throw 'Python.org installer SHA-256 did not match the pinned official release checksum.' }
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
            $signature.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false) -ne 'Python Software Foundation') {
            throw 'Python.org installer Authenticode signature is not valid or is not signed by the Python Software Foundation.'
        }
        $installArgs = @('/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0',
                         'Include_pip=1', 'Include_test=0', 'AssociateFiles=0', 'Shortcuts=0')
        Write-Host 'Installing Python for the current user without changing PATH or file associations...'
        $result = Invoke-NativeCommand $installer $installArgs 900000
        if ($result.ExitCode -ne 0) { throw ('The verified Python.org installer failed with exit code ' + $result.ExitCode + '. ' + $result.StdErr) }
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-OrInstallPython314 {
    $python = Get-Python314
    if ($python) { return $python }

    $winget = Get-WingetStatus
    if ($winget.Available) {
        $exitCode = Invoke-WingetPythonInstall $winget.Executable
        if ($exitCode -eq 0) {
            $python = Get-Python314
            if ($python) { return $python }
            Write-Warning 'WinGet reported success, but Python 3.14 could not be found and verified. Trying the official Python.org installer.'
        } else {
            Write-Warning ('WinGet could not install Python 3.14 (exit code ' + $exitCode + '). Trying the official Python.org installer.')
        }
    } else {
        Write-Warning $winget.Diagnostic
        Write-Host 'Continuing with the signed and SHA-256-verified Python.org installer.'
    }

    Install-OfficialPython314
    $python = Get-Python314
    if (-not $python) { throw 'Python installation finished, but no executable reporting CPython 3.14 could be found. No fixed install path was assumed.' }
    return $python
}

function Get-InstallerArguments {
    $arguments = @()
    # Windows does not ship SoundCloud; install every supported Windows app
    # by default instead of making the normal install fail on that component.
    $arguments += '--allow-partial'
    if ($Preview) { $arguments += '--preview' }
    if ($DeferSystem) { $arguments += '--defer-system' }
    if ($Prefix) { $arguments += @('--prefix', $Prefix) }
    if ($Components) { $arguments += @('--components', $Components) }
    return $arguments
}

function Invoke-TToolsInstall {
    if ($PSVersionTable.PSVersion.Major -le 5) {
        # Windows PowerShell 5.1's .NET Framework otherwise defaults to older TLS versions.
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }
    $python = Get-OrInstallPython314
    $work = Join-Path ([IO.Path]::GetTempPath()) ('ttools-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    try {
        if ($LocalPackage) {
            $scriptPath = Join-Path $script:InstallerRoot 'install-local.py'
            if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf) -or
                -not (Test-Path -LiteralPath (Join-Path $script:InstallerRoot 'bundle.json') -PathType Leaf)) {
                throw 'The local package is incomplete. Extract the complete Windows release ZIP before running Install-ttools.cmd.'
            }
            $arguments = @($scriptPath) + (Get-InstallerArguments)
        } else {
            $scriptPath = Join-Path $work 'bootstrap.py'
            Invoke-WebRequest -UseBasicParsing -Uri $script:BootstrapUrl -OutFile $scriptPath -ErrorAction Stop
            $arguments = @($scriptPath) + (Get-InstallerArguments)
        }
        Write-Host ('Using verified Python 3.14: ' + $python)
        $result = Invoke-NativeCommand $python $arguments 7200000
        if ($result.StdOut) { Write-Host $result.StdOut.TrimEnd() }
        if ($result.StdErr) { Write-Host $result.StdErr.TrimEnd() }
        if ($result.ExitCode -ne 0) { throw 'ttools installation failed; see the installer output above.' }
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $DefinitionsOnly) { Invoke-TToolsInstall }
