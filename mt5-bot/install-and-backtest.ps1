# Installerer en EA i MetaTrader 5, compiler den og kører en backtest.
#
# Brug (PowerShell, i mappen med denne fil og .mq5-filen):
#   1. Luk MetaTrader 5 helt
#   2. Anbefalet bot (NAS100, dagscandles):
#      powershell -ExecutionPolicy Bypass -File .\install-and-backtest.ps1 -Expert NasDipEA -Symbol NAS100 -Period D1 -Years 10
#
# Valgfrit: -Symbol med Vantages præcise navn (fx "NAS100.r"), -Years, -NoBacktest

param(
    [string]$Expert = "NasDipEA",
    [string]$Symbol = "NAS100",
    [string]$Period = "D1",
    [int]$Years = 10,
    [int]$Model = 1,   # 1 = 1-minut OHLC (hurtig, fin til D1), 4 = rigtige ticks
    [int]$Deposit = 200,
    [switch]$NoBacktest
)

$ErrorActionPreference = "Stop"
$eaSource = Join-Path $PSScriptRoot "$Expert.mq5"
if (-not (Test-Path $eaSource)) { throw "Kan ikke finde $Expert.mq5 ved siden af scriptet." }

# --- Find MT5-installationen og dens datamappe (origin.txt peger på installationen)
$terminalsRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
$candidates = @()
foreach ($dir in Get-ChildItem $terminalsRoot -Directory -ErrorAction SilentlyContinue) {
    $origin = Join-Path $dir.FullName "origin.txt"
    if (-not (Test-Path $origin)) { continue }
    $installDir = (Get-Content $origin -Raw -Encoding Unicode).Trim()
    $terminalExe = Join-Path $installDir "terminal64.exe"
    if (Test-Path $terminalExe) {
        $candidates += [pscustomobject]@{ DataDir = $dir.FullName; InstallDir = $installDir; Terminal = $terminalExe }
    }
}
if ($candidates.Count -eq 0) { throw "Fandt ingen MetaTrader 5-installation. Har du startet MT5 mindst én gang?" }

$mt5 = $candidates | Where-Object { $_.InstallDir -match "Vantage" } | Select-Object -First 1
if (-not $mt5) { $mt5 = $candidates[0] }
Write-Host "MT5 fundet:  $($mt5.InstallDir)"
Write-Host "Datamappe:   $($mt5.DataDir)"

# --- Kopiér og compile
$expertsDir = Join-Path $mt5.DataDir "MQL5\Experts"
$eaTarget = Join-Path $expertsDir "$Expert.mq5"
Copy-Item $eaSource $eaTarget -Force
Write-Host "Kopieret til $eaTarget"

$metaEditor = Join-Path $mt5.InstallDir "metaeditor64.exe"
$compileLog = Join-Path $expertsDir "$Expert.compile.log"
Start-Process -FilePath $metaEditor -ArgumentList "/compile:`"$eaTarget`"", "/log:`"$compileLog`"" -Wait
$logText = Get-Content $compileLog -Raw -Encoding Unicode
Write-Host $logText
if (-not (Test-Path (Join-Path $expertsDir "$Expert.ex5")) -or $logText -notmatch "0 errors") {
    throw "Compile fejlede. Send indholdet af $compileLog til Claude."
}
Write-Host "Compile OK." -ForegroundColor Green

if ($NoBacktest) { exit 0 }

# --- Backtest via tester-konfiguration
$to = Get-Date
$from = $to.AddYears(-$Years)
$reportName = "${Expert}_backtest"
$ini = @"
[Tester]
Expert=$Expert.ex5
Symbol=$Symbol
Period=$Period
Model=$Model
FromDate=$($from.ToString("yyyy.MM.dd"))
ToDate=$($to.ToString("yyyy.MM.dd"))
Deposit=$Deposit
Currency=USD
Optimization=0
Report=$reportName
ReplaceReport=1
ShutdownTerminal=1
"@
$iniPath = Join-Path $mt5.DataDir "tester_$Expert.ini"
Set-Content -Path $iniPath -Value $ini -Encoding Unicode

Write-Host "Kører backtest af $Expert på $Symbol $Period fra $($from.ToString('yyyy-MM-dd')). Det kan tage flere minutter (MT5 henter tick-data første gang)..."
Start-Process -FilePath $mt5.Terminal -ArgumentList "/config:`"$iniPath`"" -Wait

$report = Get-ChildItem $mt5.DataDir -Filter "$reportName*.htm*" -Recurse -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($report) {
    Write-Host "Rapport: $($report.FullName)" -ForegroundColor Green
    Start-Process $report.FullName
} else {
    Write-Host "Ingen rapport fundet. Var MT5 lukket, før scriptet startede? Findes symbolet '$Symbol' på din konto?" -ForegroundColor Yellow
}
