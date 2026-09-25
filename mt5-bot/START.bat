@echo off
rem Dobbeltklik: installerer NasDipEA i Vantage MT5, compiler og kører en 10-års backtest.
rem Luk MetaTrader 5 før du starter.
cd /d "%~dp0"
echo.
echo  NasDipEA - installation og backtest
echo  ===================================
echo  Luk MetaTrader 5 helt, foer du fortsaetter.
echo.
set /p SYM=Hvad hedder NAS100 hos Vantage? (tryk Enter for NAS100): 
if "%SYM%"=="" set SYM=NAS100
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-and-backtest.ps1" -Expert NasDipEA -Symbol "%SYM%" -Period D1 -Years 10
echo.
pause
