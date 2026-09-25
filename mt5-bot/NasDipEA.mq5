//+------------------------------------------------------------------+
//|                                                    NasDipEA.mq5  |
//|  "Køb dykket" på NAS100 (IBS mean reversion) med trendfilter.    |
//|                                                                  |
//|  Regler (vurderes ved hver lukket dagscandle, D1):               |
//|   - Køb når: luk > SMA200 OG IBS < 0.2                           |
//|       IBS = (luk - low) / (high - low) = lukkede tæt på bunden   |
//|   - Sælg når: en dag lukker over den foregående dags high        |
//|   - Nødstop: 3 x ATR(14) under indgang                           |
//|   - Kun køb (long), maks. én position                            |
//|   - Størrelse: kursværdi = konto x InpExposure (1.0 = ingen      |
//|     gearing ud over hvad kontoen er værd)                        |
//+------------------------------------------------------------------+
#property copyright "antonvang"
#property version   "1.00"
#property description "NAS100 IBS-dip-køb med SMA200-trendfilter"

#include <Trade\Trade.mqh>

input group "Strategi"
input int    InpSMAPeriod   = 200;  // Trendfilter: SMA-periode (D1)
input double InpIBSLevel    = 0.2;  // Køb når IBS er under dette
input int    InpATRPeriod   = 14;   // ATR-periode til nødstop
input double InpStopATR     = 3.0;  // Nødstop = ATR x dette

input group "Størrelse og risiko"
input double InpExposure       = 1.0;  // Kursværdi som andel af konto (1.0 = 1x)
input double InpMaxMinLotRatio = 1.5;  // Hvis min. lot er større end konto x dette: spring over
input double InpMaxDailyLossPct = 10.0; // Luk alt ved dette tab på en dag (%)
input int    InpMaxSpreadPoints = 0;   // Maks. spread i points (0 = ingen grænse)

input group "Diverse"
input ulong InpMagic = 20260926; // Magic number

CTrade   trade;
int      hSMA = INVALID_HANDLE;
int      hATR = INVALID_HANDLE;
datetime g_lastBar = 0;
int      g_dayKey = -1;
double   g_dayStartEquity = 0.0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpExposure <= 0.0 || InpExposure > 3.0)
     {
      Print("InpExposure skal være mellem 0 og 3");
      return INIT_PARAMETERS_INCORRECT;
     }
   hSMA = iMA(_Symbol, PERIOD_D1, InpSMAPeriod, 0, MODE_SMA, PRICE_CLOSE);
   hATR = iATR(_Symbol, PERIOD_D1, InpATRPeriod);
   if(hSMA == INVALID_HANDLE || hATR == INVALID_HANDLE)
     {
      Print("Kunne ikke oprette indikatorer");
      return INIT_FAILED;
     }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(hSMA);
   IndicatorRelease(hATR);
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   CheckDailyLoss();

   datetime barTime = iTime(_Symbol, PERIOD_D1, 0);
   if(barTime == 0 || barTime == g_lastBar)
      return;

   //--- dagscandlen i går (index 1) og dagen før (index 2)
   double h1 = iHigh(_Symbol, PERIOD_D1, 1);
   double l1 = iLow(_Symbol, PERIOD_D1, 1);
   double c1 = iClose(_Symbol, PERIOD_D1, 1);
   double h2 = iHigh(_Symbol, PERIOD_D1, 2);
   double sma[], atr[];
   if(CopyBuffer(hSMA, 0, 1, 1, sma) < 1 || CopyBuffer(hATR, 0, 1, 1, atr) < 1 ||
      h1 <= 0.0 || h2 <= 0.0)
      return;  // data ikke klar endnu; prøv igen næste tick
   g_lastBar = barTime;

   ulong ticket = OurPosition();
   if(ticket != 0)
     {
      //--- exit: gårsdagens luk over forrige dags high
      if(c1 > h2)
        {
         if(!trade.PositionClose(ticket))
            PrintFormat("Lukning fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
        }
      ShowStatus(c1 > h2 ? "Exit-signal: lukker" : "Position åben, venter på exit");
      return;
     }

   double range = h1 - l1;
   if(range <= 0.0)
      return;
   double ibs = (c1 - l1) / range;
   bool entry = c1 > sma[0] && ibs < InpIBSLevel;
   if(!entry)
     {
      ShowStatus(StringFormat("Venter. Luk %s SMA%d, IBS %.2f", c1 > sma[0] ? "over" : "under",
                              InpSMAPeriod, ibs));
      return;
     }
   if(InpMaxSpreadPoints > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPoints)
     {
      ShowStatus("Signal, men spread for høj");
      g_lastBar = 0;  // prøv igen senere i dag
      return;
     }
   OpenLong(atr[0]);
  }

//+------------------------------------------------------------------+
void OpenLong(double atrValue)
  {
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double lots = CalcLots(ask);
   if(lots <= 0.0)
      return;
   double sl = NormalizeDouble(ask - atrValue * InpStopATR, _Digits);
   if(trade.Buy(lots, _Symbol, ask, sl, 0.0, "NasDip"))
      PrintFormat("Køb %.2f lot til %.2f, nødstop %.2f", lots, ask, sl);
   else
      PrintFormat("Køb fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
//| Lots så kursværdien = equity x InpExposure                      |
//+------------------------------------------------------------------+
double CalcLots(double price)
  {
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;
   double notionalPerLot = price / tickSize * tickValue;  // i kontovaluta
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double target = equity * InpExposure;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = MathFloor(target / notionalPerLot / step + 1e-8) * step;
   if(lots < minL)
     {
      if(minL * notionalPerLot <= equity * InpMaxMinLotRatio)
         lots = minL;
      else
        {
         PrintFormat("Springer over: mindste lot har kursværdi %.2f, kontoen er %.2f", minL * notionalPerLot, equity);
         return 0.0;
        }
     }
   lots = MathMin(lots, maxL);
   int volDigits = (int)MathMax(0, MathCeil(-MathLog10(step)));
   lots = NormalizeDouble(lots, volDigits);

   double margin = 0.0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, price, margin) ||
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.8)
     {
      PrintFormat("Springer over: ikke nok fri margin (kræver %.2f)", margin);
      return 0.0;
     }
   return lots;
  }

//+------------------------------------------------------------------+
void CheckDailyLoss()
  {
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   int key = t.year * 1000 + t.day_of_year;
   if(key != g_dayKey)
     {
      g_dayKey = key;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
     }
   if(InpMaxDailyLossPct <= 0.0 || g_dayStartEquity <= 0.0)
      return;
   if(AccountInfoDouble(ACCOUNT_EQUITY) <= g_dayStartEquity * (1.0 - InpMaxDailyLossPct / 100.0))
     {
      ulong ticket = OurPosition();
      if(ticket != 0 && trade.PositionClose(ticket))
         Print("Dagligt tabsstop ramt: position lukket");
     }
  }

//+------------------------------------------------------------------+
ulong OurPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket != 0 && PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
         return ticket;
     }
   return 0;
  }

//+------------------------------------------------------------------+
void ShowStatus(string status)
  {
   Comment(StringFormat("NasDipEA | %s\nEquity: %.2f | Eksponering: %.1fx", status,
                        AccountInfoDouble(ACCOUNT_EQUITY), InpExposure));
  }
//+------------------------------------------------------------------+
