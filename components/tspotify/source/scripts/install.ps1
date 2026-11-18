$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'tspotify requires Windows x64.' }
$asset = 'tspotify-windows-x86_64.zip'
$releasePath = 'latest/download'
if ($env:TSPOTIFY_RELEASE) {
    if ($env:TSPOTIFY_RELEASE -notmatch '^v?[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid release' }
    $releasePath = 'download/' + $env:TSPOTIFY_RELEASE
}
$baseUrl = 'https://github.com/user9x21imi/tspotify/releases/' + $releasePath
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('tspotify-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $taskTemp | Out-Null
try {
    Write-Host '+-- installing tspotify ---------------------------------------+' -ForegroundColor Green
    $zipPath = Join-Path $taskTemp $asset
    Invoke-WebRequest "$baseUrl/$asset" -OutFile $zipPath -UseBasicParsing
    $checksumPath = Join-Path $taskTemp 'SHA256SUMS.txt'
    Invoke-WebRequest "$baseUrl/SHA256SUMS.txt" -OutFile $checksumPath -UseBasicParsing
    $checksums = Get-Content $checksumPath -Raw -Encoding UTF8
    $matching = @($checksums -split "`n" | Where-Object { $_ -match ('\s+' + [regex]::Escape($asset) + '\s*$') })
    if ($matching.Count -ne 1) { throw 'Missing or ambiguous release checksum.' }
    $expected = ($matching[0].Trim() -split '\s+')[0]
    if ($expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid SHA-256 checksum.' }
    $actual = (Get-FileHash $zipPath -Algorithm SHA256).Hash
    if ($actual -ne $expected) { throw 'Checksum mismatch. Installation stopped.' }
    $unpacked = Join-Path $taskTemp 'unpacked'
    Expand-Archive $zipPath -DestinationPath $unpacked
    $incoming = Join-Path $unpacked 'tspotify'
    if (-not (Test-Path (Join-Path $incoming 'tspotify.exe'))) { throw 'Invalid release archive.' }
    $root = Join-Path $env:LOCALAPPDATA 'tspotify'
    $appPath = Join-Path $root 'app'
    $previous = Join-Path $root 'app.previous'
    New-Item -ItemType Directory -Force $root | Out-Null
    if (Test-Path $appPath) {
        if (Test-Path $previous) { Remove-Item -Recurse -Force $previous }
        Move-Item $appPath $previous
    }
    Move-Item $incoming $appPath
    $userPath = [string][Environment]::GetEnvironmentVariable('Path', 'User')
    if (($userPath -split ';') -notcontains $appPath) {
        [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $appPath), 'User')
    }
    $env:Path = $env:Path + ';' + $appPath
    $shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'tspotify.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcut)
    $link.TargetPath = Join-Path $appPath 'tspotify.exe'
    $link.WorkingDirectory = $appPath
    $link.Save()
    & (Join-Path $appPath 'tspotify.exe') --version
    Write-Host 'Installed. Run tspotify, or use its Start Menu shortcut.' -ForegroundColor Green
} finally {
    Remove-Item -Recurse -Force $taskTemp -ErrorAction SilentlyContinue
}

