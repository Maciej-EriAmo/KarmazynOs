@echo off
REM karmazyn — launcher Windows (Kernel Karmazyn)
REM Preferuje uklad kernel\ + software\ (jak Docker).
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if exist "%ROOT%\kernel" if exist "%ROOT%\software" (
  set "PYTHONPATH=%ROOT%\kernel;%ROOT%\software;%PYTHONPATH%"
  python "%ROOT%\software\karmazyn_boot.py" %*
  exit /b %ERRORLEVEL%
)
if defined KARMAZYN_HOME (
  set "PYTHONPATH=%KARMAZYN_HOME%;%PYTHONPATH%"
  python "%KARMAZYN_HOME%\karmazyn_boot.py" %*
) else (
  set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
  python "%ROOT%\karmazyn_boot.py" %*
)
