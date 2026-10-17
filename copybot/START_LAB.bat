@echo off
rem Dobbeltklik: Mars Command Center - forskningsflaade + dashboard. Kun simuleret handel, ingen rigtige penge.
cd /d "%~dp0"
echo.
echo  Mars Command Center - forskningsflaade (paper, ingen rigtige penge)
echo  ===================================================================

py -3 --version >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  python --version >nul 2>nul
  if errorlevel 1 goto nopython
  set "PY=python"
)

echo.
echo  Starter dashboardet i et minimeret vindue ("Lab dashboard") ...
start "Lab dashboard" /min %PY% -m lab web --port 8770
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:8770
echo.
echo  Forskningsflaaden koerer nu i DETTE vindue.
echo  - Stop flaaden: luk dette vindue, eller tryk Pause/Stop i dashboardet.
echo  - Stop dashboardet: luk vinduet "Lab dashboard" paa proceslinjen.
echo.
%PY% -m lab fleet
goto end

:nopython
echo.
echo  Python er ikke installeret.
echo  1. Hent det fra https://www.python.org/downloads/
echo  2. Saet flueben i "Add python.exe to PATH" under installationen.
echo  3. Dobbeltklik paa denne fil igen.

:end
echo.
pause
