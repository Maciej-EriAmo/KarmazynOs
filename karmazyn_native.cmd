@echo off
REM Find and run native karmazyn_shell — no Python.
setlocal EnableExtensions
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "SHELL="
if exist "%ROOT%\dist\prefix\bin\karmazyn_shell.exe" set "SHELL=%ROOT%\dist\prefix\bin\karmazyn_shell.exe"
if not defined SHELL if exist "%ROOT%\native\karmazyn_shell\target\release\karmazyn_shell.exe" set "SHELL=%ROOT%\native\karmazyn_shell\target\release\karmazyn_shell.exe"
if not defined SHELL if exist "%ROOT%\native\karmazyn_shell\target\debug\karmazyn_shell.exe" set "SHELL=%ROOT%\native\karmazyn_shell\target\debug\karmazyn_shell.exe"

if not defined SHELL (
  echo KarmazynOs: brak karmazyn_shell.exe
  echo Zbuduj bez Pythona:
  echo   powershell -File native\bootstrap_from_scratch.ps1 -SkipC
  echo albo:
  echo   cd native\karmazyn_shell ^&^& cargo build --release
  exit /b 2
)

"%SHELL%" %*
exit /b %ERRORLEVEL%
