@echo off
REM Karmazyn.bat — start KarmazynOs (native shell = default, no Python)
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%USERPROFILE%\.cargo\bin" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

if "%~1"=="" goto menu

echo.%*| findstr /i "\-\-python" >nul
if not errorlevel 1 goto python_args
call "%~dp0karmazyn_native.cmd" %*
exit /b %ERRORLEVEL%

:python_args
python "%~dp0start.py" %*
exit /b %ERRORLEVEL%

:menu
echo.
echo ========================================================
echo   KarmazynOs
echo ========================================================
echo   1  Native shell          [domyslny, BEZ Pythona]
echo   2  Demo native (smoke.ksh)
echo   3  Boot Python           (opcjonalna skora hosta)
echo   4  Demo Python
echo   5  Zbuduj native shell   (cargo, bez Pythona)
echo   0  Wyjscie
echo ========================================================
set /p CHOICE=  wybor: 

if "%CHOICE%"=="" set CHOICE=1
if "%CHOICE%"=="0" exit /b 0
if "%CHOICE%"=="1" goto native
if "%CHOICE%"=="2" goto demo_native
if "%CHOICE%"=="3" goto python
if "%CHOICE%"=="4" goto demo_python
if "%CHOICE%"=="5" goto build
echo Nieznany wybor.
goto menu

:native
call "%~dp0karmazyn_native.cmd"
exit /b %ERRORLEVEL%

:demo_native
call "%~dp0karmazyn_native.cmd" "%~dp0native\karmazyn_shell\examples\smoke.ksh"
exit /b %ERRORLEVEL%

:python
python "%~dp0start.py" --rust
exit /b %ERRORLEVEL%

:demo_python
python "%~dp0start.py" --rust --demo
exit /b %ERRORLEVEL%

:build
cd /d "%~dp0native\karmazyn_shell"
cargo build --release
if errorlevel 1 (
  echo Brak cargo? https://rustup.rs/
  pause
  exit /b 1
)
cd /d "%~dp0"
echo OK: native\karmazyn_shell\target\release\karmazyn_shell.exe
pause
exit /b 0
