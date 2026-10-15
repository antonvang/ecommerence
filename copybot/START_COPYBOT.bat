@echo off
rem Dobbeltklik: CopyBot - kopierer memecoin-wallets paa Solana med FALSKE penge (paper trading).
cd /d "%~dp0"
echo.
echo  CopyBot - paper trading (ingen rigtige penge, ingen private noegler)
echo  =====================================================================

py -3 --version >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  python --version >nul 2>nul
  if errorlevel 1 goto nopython
  set "PY=python"
)

echo.
echo  1 = Backtest: test dine wallets paa de sidste 14 dage (hurtigt svar)
echo  2 = Paper trading: foelg wallets live med falske penge + dashboard
echo  3 = Vis dashboard for seneste backtest
echo  4 = Rapport over paper trading (tal)
echo.
choice /c 1234 /n /m "Vaelg 1, 2, 3 eller 4: "
if errorlevel 4 goto report
if errorlevel 3 goto dash
if errorlevel 2 goto paper
%PY% copybot.py backtest
goto end

:paper
echo.
echo  Dashboardet aabner i din browser. Luk dette vindue for at stoppe botten.
%PY% copybot.py paper
goto end

:dash
%PY% copybot.py dashboard
goto end

:report
%PY% copybot.py report
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
