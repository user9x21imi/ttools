$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Resolve-WinGet {
    $command = Get-Command winget.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source -and (Test-Path $command.Source)) { return $command.Source }

    $aliasPath = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
    if (Test-Path $aliasPath) { return $aliasPath }

    $package = Get-AppxPackage -Name Microsoft.DesktopAppInstaller -ErrorAction SilentlyContinue |
        Sort-Object { try { [version]$_.Version } catch { [version]'0.0' } } -Descending |
        Select-Object -First 1
    if ($package) {
        # App Installer can be present before its execution alias is registered
        # for a newly signed-in Windows user.
        try {
            Add-AppxPackage -RegisterByFamilyName -MainPackage $package.PackageFamilyName -ErrorAction Stop
        } catch { }
        if (Test-Path $aliasPath) { return $aliasPath }
        if ($package.InstallLocation) {
            $packagedClient = Join-Path $package.InstallLocation 'winget.exe'
            if (Test-Path $packagedClient) { return $packagedClient }
        }
    }
    return $null
}

function Resolve-Python313 {
    $fixed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    $candidates = @($fixed)
    $command = Get-Command python3.13.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source) { $candidates += $command.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path $candidate)) { continue }
        $version = (& $candidate --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $version -match '^Python 3\.13(?:\.\d+)?$') { return $candidate }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher -and $launcher.Source) {
        $candidate = (& $launcher.Source -3.13 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

try {
    $py = Resolve-Python313
    $gui = Join-Path $env:ProgramFiles 'OpenVPN\bin\openvpn-gui.exe'
    $needsDependencies = (-not $py) -or (-not (Test-Path $gui))
    $winget = if ($needsDependencies) { Resolve-WinGet } else { $null }
    if (-not $py) {
        if (-not $winget) { throw 'Python 3.13 is missing and WinGet is unavailable. Install Python 3.13 from python.org or install/register Microsoft App Installer, then retry.' }
        & $winget install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
        $py = Resolve-Python313
    }
    if (-not $py) { throw 'Python 3.13 executable was not found after installation.' }
    if (-not (Test-Path $gui)) {
        if (-not $winget) { throw 'OpenVPN Community is missing and WinGet is unavailable. Install it from openvpn.net/community-downloads, or install/register Microsoft App Installer, then retry.' }
        & $winget install --id OpenVPNTechnologies.OpenVPN --exact --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'OpenVPN installation failed.' }
    }
    $work = Join-Path $env:TEMP ('tvpn-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        Invoke-WebRequest -UseBasicParsing 'https://codeload.github.com/user9x21imi/tvpn/zip/refs/heads/main' -OutFile "$work\source.zip"
        Expand-Archive "$work\source.zip" "$work\source"
        $dest = Join-Path $env:LOCALAPPDATA 'TVPN'
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item "$work\source\tvpn-main\*" $dest -Recurse -Force
    } finally { Remove-Item $work -Recurse -Force }
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $setup = Join-Path $dest 'platforms\windows\install.ps1'
    $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$setup+'"'),'-User',('"'+$user+'"'))
    if ($process.ExitCode -ne 0) { throw 'Administrator setup failed or was cancelled.' }
    & $py -m venv "$dest\.venv"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment.' }
    & "$dest\.venv\Scripts\python.exe" -m pip install -r "$dest\requirements-windows.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install Python dependencies.' }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'TVPN.lnk'))
    $link.TargetPath = Join-Path $dest 'start-windows.cmd'
    $link.WorkingDirectory = $dest
    $link.Save()
    $commands = Join-Path $env:LOCALAPPDATA 'TVPN\bin'
    New-Item -ItemType Directory -Force -Path $commands | Out-Null
    ('@echo off' + "`r`n" + 'call "'+$dest+'\start-windows.cmd" %*') | Set-Content "$commands\tvpn.cmd" -Encoding ASCII
    $userPath = [Environment]::GetEnvironmentVariable('Path','User')
    if (($userPath -split ';') -notcontains $commands) { [Environment]::SetEnvironmentVariable('Path',($userPath+';'+$commands),'User') }
    Write-Host 'TVPN installed. Sign out and back in once to activate VPN permissions. Then open TVPN from Start or type tvpn in a new terminal.'
    Read-Host 'Press Enter to close'
} catch {
    Write-Host $_ -ForegroundColor Red
    Read-Host 'Installation failed. Press Enter to close'
    exit 1
}
