@echo off
REM karmazyn.cmd — start KarmazynOs
REM Domyślnie: native shell (bez Pythona).
REM Skóra CPython: karmazyn.cmd --python
setlocal EnableExtensions
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.%*| findstr /i "\-\-python" >nul
if not errorlevel 1 goto python_boot

call "%ROOT%\karmazyn_native.cmd" %*
exit /b %ERRORLEVEL%

:python_boot
if exist "%USERPROFILE%\.cargo\bin" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "KARMAZYN_SUBSTRATE=native"
set "PYTHONPATH=%ROOT%;%ROOT%\archiwum\kernel_python;%ROOT%\software;%ROOT%\native;%PYTHONPATH%"
if exist "%ROOT%\software\karmazyn_boot.py" (
  python "%ROOT%\software\karmazyn_boot.py" %*
) else (
  echo brak software\karmazyn_boot.py
  exit /b 1
)
exit /b %ERRORLEVEL%
