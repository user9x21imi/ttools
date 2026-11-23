@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
set "TTOOLS_INSTALL_PREVIEW="
set "TTOOLS_INSTALL_ALLOW_PARTIAL="
set "TTOOLS_INSTALL_PREFIX="
set "TTOOLS_INSTALL_COMPONENTS="
set "TTOOLS_INSTALL_DEFER_SYSTEM="
set "TTOOLS_INSTALL_LOG_PATH="
set "TTOOLS_LOCAL_PACKAGE_ROOT=%~dp0"

:parse_args
if "%~1"=="" goto run_installer
if /i "%~1"=="-Preview" goto set_preview
if /i "%~1"=="-AllowPartial" goto set_allow_partial
if /i "%~1"=="-Prefix" goto set_prefix
if /i "%~1"=="-Components" goto set_components
if /i "%~1"=="-DeferSystem" goto set_defer_system
if /i "%~1"=="-LogPath" goto set_log_path
echo Unsupported installer option.
goto failed

:run_installer
rem Invoke the bundled text as a script block; no execution-policy change or py command is needed.
powershell.exe -NoLogo -NoProfile -Command "$installer = Join-Path (Get-Location) 'install.ps1'; $script = [scriptblock]::Create([IO.File]::ReadAllText($installer)); $options = @{ LocalPackage = $true }; if ($env:TTOOLS_INSTALL_PREVIEW -eq '1') { $options.Preview = $true }; if ($env:TTOOLS_INSTALL_ALLOW_PARTIAL -eq '1') { $options.AllowPartial = $true }; if ($env:TTOOLS_INSTALL_DEFER_SYSTEM -eq '1') { $options.DeferSystem = $true }; if ($env:TTOOLS_INSTALL_PREFIX) { $options.Prefix = $env:TTOOLS_INSTALL_PREFIX }; if ($env:TTOOLS_INSTALL_COMPONENTS) { $options.Components = $env:TTOOLS_INSTALL_COMPONENTS }; if ($env:TTOOLS_INSTALL_LOG_PATH) { $options.LogPath = $env:TTOOLS_INSTALL_LOG_PATH }; & $script @options"
if errorlevel 1 (
  echo Installation failed. See the installer output above.
  if /i not "%TTOOLS_INSTALLER_NO_PAUSE%"=="1" pause
  exit /b 1
)
echo.
echo Installation complete. Open a new terminal and run: ttools
if /i not "%TTOOLS_INSTALLER_NO_PAUSE%"=="1" pause
exit /b 0

:failed
if /i not "%TTOOLS_INSTALLER_NO_PAUSE%"=="1" pause
exit /b 2

:set_preview
set "TTOOLS_INSTALL_PREVIEW=1"
shift
goto parse_args

:set_allow_partial
set "TTOOLS_INSTALL_ALLOW_PARTIAL=1"
shift
goto parse_args

:set_prefix
shift
if "%~1"=="" goto missing_value
set "TTOOLS_INSTALL_PREFIX=%~1"
shift
goto parse_args

:set_components
shift
if "%~1"=="" goto missing_value
set "TTOOLS_INSTALL_COMPONENTS=%~1"
shift
goto parse_args

:set_defer_system
set "TTOOLS_INSTALL_DEFER_SYSTEM=1"
shift
goto parse_args

:set_log_path
shift
if "%~1"=="" goto missing_value
set "TTOOLS_INSTALL_LOG_PATH=%~1"
shift
goto parse_args

:missing_value
echo A value is missing for the installer option.
goto failed
