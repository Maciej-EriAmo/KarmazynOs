@echo off
REM karmazyn.cmd — szybki start KarmazynOs (bez menu)
REM Menu z wyborem: Karmazyn.bat  /  python start.py
REM Substrat DOMYSLNIE: native Rust. Python: set KARMAZYN_SUBSTRATE=python
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if exist "%USERPROFILE%\.cargo\bin" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

REM flaga --python / --rust z linii komend
set "ARGS=%*"
echo.%ARGS% | findstr /i "\-\-python" >nul && set "KARMAZYN_SUBSTRATE=python"
echo.%ARGS% | findstr /i "\-\-rust \-\-native" >nul && set "KARMAZYN_SUBSTRATE=native"
if not defined KARMAZYN_SUBSTRATE set "KARMAZYN_SUBSTRATE=native"

set "PYTHONPATH=%ROOT%;%ROOT%\kernel;%ROOT%\software;%ROOT%\native;%PYTHONPATH%"

if exist "%ROOT%\software\karmazyn_boot.py" (
  python "%ROOT%\software\karmazyn_boot.py" %*
) else (
  python "%ROOT%\karmazyn_boot.py" %*
)
exit /b %ERRORLEVEL%
