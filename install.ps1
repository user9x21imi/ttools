param([switch]$AllowPartial,[switch]$Preview,[string]$Prefix)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidate = & py -3.14 -c 'import sys;print(sys.executable)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate.Trim() }
}
if (-not $python) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer (winget), then rerun.' }
    & winget install --id Python.Python.3.14 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    if (-not (Test-Path $python)) { throw 'Python 3.14 not found. Open a new terminal and retry.' }
}
$work = Join-Path ([IO.Path]::GetTempPath()) ('ttools-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $script = Join-Path $work 'bootstrap.py'
    Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/user9x21imi/ttools/main/bootstrap.py' -OutFile $script
    $arguments = @($script)
    if ($AllowPartial) { $arguments += '--allow-partial' }
    if ($Preview) { $arguments += '--preview' }
    if ($Prefix) { $arguments += @('--prefix',$Prefix) }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'ttools installation failed; see output above.' }
} finally { Remove-Item $work -Recurse -Force }
