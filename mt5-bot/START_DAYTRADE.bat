@echo off
rem Dobbeltklik: installerer NasDayEA (daytrading) i Vantage MT5, compiler og backtester.
cd /d "%~dp0"
echo.
echo  NasDayEA - daytrading paa NAS100 (1 handel om dagen, lukker foer luk)
echo  =====================================================================
echo  Luk MetaTrader 5 helt, foer du fortsaetter.
echo.
set /p SYM=Hvad hedder NAS100 hos Vantage? (tryk Enter for NAS100): 
if "%SYM%"=="" set SYM=NAS100
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-and-backtest.ps1" -Expert NasDayEA -Symbol "%SYM%" -Period H1 -Years 5 -Model 1
echo.
pause
