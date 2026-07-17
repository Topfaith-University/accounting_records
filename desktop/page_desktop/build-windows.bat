@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  Page Desktop - Windows build script
rem
rem  Produces a portable PageDesktop-<version>-portable.exe in
rem  .\release\ - no installer, no admin rights, just double-click.
rem
rem  Run this from anywhere; it locates itself via %~dp0.
rem
rem  Prerequisites on this Windows machine:
rem    - Node.js 20+ (https://nodejs.org) - includes npm
rem    - Internet access (npm install downloads packages; the
rem      electron-builder step also downloads Electron's Windows
rem      binaries the first time it runs)
rem    - better-sqlite3 usually installs from a prebuilt binary, so
rem      you normally do NOT need a C++ compiler. If a step below
rem      fails during "npm install" or "electron-rebuild" mentioning
rem      node-gyp/MSBuild, install "Visual Studio Build Tools" (the
rem      "Desktop development with C++" workload) and Python 3, then
rem      re-run this script.
rem ============================================================

cd /d "%~dp0"

echo.
echo === Page Desktop - Windows build ===
echo Working directory: %cd%
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo ERROR: Node.js was not found on PATH.
    echo Install it from https://nodejs.org ^(LTS version^) and re-run this script.
    goto :error
)

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found on PATH. It normally ships with Node.js -
    echo try reinstalling Node.js from https://nodejs.org.
    goto :error
)

for /f "delims=" %%v in ('node --version') do echo Node.js: %%v
for /f "delims=" %%v in ('npm --version') do echo npm: %%v
echo.

echo [1/4] Installing dependencies for the desktop app...
call npm install
if errorlevel 1 (
    echo ERROR: "npm install" failed. See the output above for details.
    goto :error
)
echo.

echo [2/4] Type-checking and bundling the Electron main process...
call npm run build
if errorlevel 1 (
    echo ERROR: "npm run build" failed. See the output above for details.
    goto :error
)
echo.

echo [3/4] Building the Angular frontend ^(this also runs "npm install"
echo        inside frontend\sage-frontend the first time^)...
call npm run build:frontend
if errorlevel 1 (
    echo ERROR: "npm run build:frontend" failed. See the output above for details.
    goto :error
)
echo.

echo [4/4] Packaging the portable Windows .exe...
echo        The first run downloads Electron's Windows binaries and can take
echo        a few minutes - this is normal.
call npx electron-builder --win portable
if errorlevel 1 (
    echo ERROR: electron-builder failed. See the output above for details.
    goto :error
)

echo.
echo === Build complete ===
echo Your portable app is in: %cd%\release\
dir /b "release\*.exe" 2>nul
echo.
echo Copy that .exe anywhere and double-click it to run - no installer needed.
echo Its data file is created next to wherever you put the .exe.
goto :end

:error
echo.
echo === Build failed - see the error above ===
exit /b 1

:end
endlocal
