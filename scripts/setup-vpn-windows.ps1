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
$process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList $argsList
if ($process.ExitCode -ne 0) { throw 'VPN administrator setup failed or was cancelled.' }
Write-Host 'VPN permissions may require signing out and back in once.'
