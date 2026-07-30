@echo off
REM Karmazyn.bat — menu startowe KarmazynOs (Rust / Python)
setlocal EnableExtensions
cd /d "%~dp0"

REM cargo w PATH (gdy jest)
if exist "%USERPROFILE%\.cargo\bin" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

if "%~1"=="" goto menu
python "%~dp0start.py" %*
exit /b %ERRORLEVEL%

:menu
echo.
echo ========================================================
echo   KarmazynOs
echo ========================================================
echo   1  Boot Rust   (native)     [domyslny]
echo   2  Boot Python (reference)
echo   3  Demo Rust
echo   4  Demo Python
echo   5  Sprawdz native
echo   6  Rust-only (cargo test)
echo   0  Wyjscie
echo ========================================================
set /p CHOICE=  wybor: 

if "%CHOICE%"=="0" exit /b 0
if "%CHOICE%"=="1" goto rust
if "%CHOICE%"=="2" goto python
if "%CHOICE%"=="3" goto demo_rust
if "%CHOICE%"=="4" goto demo_python
if "%CHOICE%"=="5" goto check
if "%CHOICE%"=="6" goto rustonly
echo Nieznany wybor.
goto menu

:rust
python "%~dp0start.py" --rust
exit /b %ERRORLEVEL%

:python
python "%~dp0start.py" --python
exit /b %ERRORLEVEL%

:demo_rust
python "%~dp0start.py" --rust --demo
exit /b %ERRORLEVEL%

:demo_python
python "%~dp0start.py" --python --demo
exit /b %ERRORLEVEL%

:check
python "%~dp0start.py" --native-check
pause
exit /b %ERRORLEVEL%

:rustonly
python "%~dp0start.py" --rust-only
pause
exit /b %ERRORLEVEL%
