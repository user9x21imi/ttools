param([Parameter(Mandatory=$true)][string]$Setup)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Microsoft App Installer / winget is required.' }
$gui = Join-Path $env:ProgramFiles 'OpenVPN\bin\openvpn-gui.exe'
if (-not (Test-Path $gui)) {
    & winget install --id OpenVPNTechnologies.OpenVPN --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'OpenVPN installation failed.' }
}
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$argsList = @('-NoProfile','-File',('"'+$Setup+'"'),'-User',('"'+$user+'"'))
$shell = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $shell) { $shell = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source }
if (-not $shell) { $shell = 'powershell.exe' }
$process = Start-Process $shell -Verb RunAs -Wait -PassThru -ArgumentList $argsList
if ($process.ExitCode -ne 0) { throw 'VPN administrator setup failed or was cancelled.' }
Write-Host 'VPN permissions may require signing out and back in once.'
