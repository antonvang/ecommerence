//+------------------------------------------------------------------+
//|                                              TrendPullbackEA.mq5 |
//|  Trendfølgende pullback-bot med fast procent-risiko pr. handel.  |
//|                                                                  |
//|  Logik:                                                          |
//|   - Trend: pris og EMA50 over EMA200 = optrend (omvendt = ned)   |
//|   - Indgang: RSI dykker under 40 i optrend og krydser op igen    |
//|     (sælg: over 60 i nedtrend og krydser ned igen)               |
//|   - Stop-loss / take-profit baseret på ATR                       |
//|   - Lotstørrelse beregnes så hver handel risikerer X % af konto  |
//|   - Daglig tabsgrænse lukker alt og stopper botten resten af dag |
//+------------------------------------------------------------------+
#property copyright "antonvang"
#property version   "1.00"
#property description "Trend + RSI pullback EA med automatisk risikostyring"

#include <Trade\Trade.mqh>

//--- Strategi
input group "Strategi"
input ENUM_TIMEFRAMES InpTimeframe     = PERIOD_H1; // Tidsramme for signaler
input int             InpFastEMA       = 50;        // Hurtig EMA
input int             InpSlowEMA       = 200;       // Langsom EMA (trendfilter)
input int             InpRSIPeriod     = 14;        // RSI periode
input double          InpRSIBuyLevel   = 40.0;      // RSI pullback-niveau for køb
input double          InpRSISellLevel  = 60.0;      // RSI pullback-niveau for salg
input int             InpATRPeriod     = 14;        // ATR periode
input double          InpSLATRMult     = 1.5;       // Stop-loss = ATR x dette
input double          InpTPATRMult     = 3.0;       // Take-profit = ATR x dette

//--- Risiko
input group "Risiko"
input double InpRiskPercent       = 1.0;  // Risiko pr. handel i % af balance
input double InpMaxDailyLossPct   = 5.0;  // Maks. dagligt tab i % (stopper for dagen)
input double InpMaxRiskOvershoot  = 1.5;  // Tillad min. lot hvis risiko <= mål x dette
input int    InpMaxSpreadPoints   = 30;   // Maks. spread i points (0 = ingen grænse)
input bool   InpUseBreakeven      = true; // Flyt SL til indgang når i profit
input double InpBreakevenR        = 1.0;  // ...efter profit = R x oprindelig risiko

//--- Handelstider (serverens tid)
input group "Handelstider"
input int  InpStartHour     = 7;    // Første time med nye handler
input int  InpEndHour       = 20;   // Ingen nye handler fra denne time
input bool InpNoFridayLate  = true; // Ingen nye handler fredag efter kl. 18

//--- Diverse
input group "Diverse"
input ulong InpMagic = 20260925; // Magic number (identificerer bottens handler)

CTrade   trade;
int      hFast = INVALID_HANDLE;
int      hSlow = INVALID_HANDLE;
int      hRSI  = INVALID_HANDLE;
int      hATR  = INVALID_HANDLE;
datetime g_lastBar = 0;
int      g_dayKey = -1;
double   g_dayStartEquity = 0.0;
bool     g_dayBlocked = false;
string   g_gvPrefix;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpRiskPercent <= 0.0 || InpRiskPercent > 5.0)
     {
      Print("InpRiskPercent skal være mellem 0 og 5");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpFastEMA >= InpSlowEMA || InpSLATRMult <= 0.0 || InpTPATRMult <= 0.0)
     {
      Print("Ugyldige strategi-parametre");
      return INIT_PARAMETERS_INCORRECT;
     }

   hFast = iMA(_Symbol, InpTimeframe, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, InpTimeframe, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   hRSI  = iRSI(_Symbol, InpTimeframe, InpRSIPeriod, PRICE_CLOSE);
   hATR  = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE ||
      hRSI == INVALID_HANDLE || hATR == INVALID_HANDLE)
     {
      Print("Kunne ikke oprette indikatorer");
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFillingBySymbol(_Symbol);

   g_gvPrefix = "TPEA_" + _Symbol + "_" + IntegerToString((long)InpMagic) + "_";
   UpdateDay();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(hFast);
   IndicatorRelease(hSlow);
   IndicatorRelease(hRSI);
   IndicatorRelease(hATR);
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   UpdateDay();

   if(CheckDailyLoss())
     {
      ShowStatus("STOPPET i dag: daglig tabsgrænse ramt");
      return;
     }

   if(InpUseBreakeven)
      ManageBreakeven();

   //--- kun vurder signaler én gang pr. ny lukket candle
   datetime barTime = iTime(_Symbol, InpTimeframe, 0);
   if(barTime == 0 || barTime == g_lastBar)
      return;
   g_lastBar = barTime;

   if(HasPosition())
     {
      ShowStatus("Position åben");
      return;
     }
   if(!TradingTimeOk())
     {
      ShowStatus("Udenfor handelstid");
      return;
     }
   if(InpMaxSpreadPoints > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPoints)
     {
      ShowStatus("Spread for høj");
      return;
     }

   double fast[], slow[], rsi[], atr[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   //--- index 0 = sidste lukkede candle, index 1 = candlen før
   if(CopyBuffer(hFast, 0, 1, 2, fast) < 2 || CopyBuffer(hSlow, 0, 1, 2, slow) < 2 ||
      CopyBuffer(hRSI, 0, 1, 2, rsi) < 2 || CopyBuffer(hATR, 0, 1, 2, atr) < 2)
      return;

   double close1 = iClose(_Symbol, InpTimeframe, 1);
   bool upTrend   = close1 > slow[0] && fast[0] > slow[0];
   bool downTrend = close1 < slow[0] && fast[0] < slow[0];
   bool buySignal  = upTrend   && rsi[1] < InpRSIBuyLevel  && rsi[0] >= InpRSIBuyLevel;
   bool sellSignal = downTrend && rsi[1] > InpRSISellLevel && rsi[0] <= InpRSISellLevel;

   if(buySignal)
      OpenTrade(ORDER_TYPE_BUY, atr[0]);
   else if(sellSignal)
      OpenTrade(ORDER_TYPE_SELL, atr[0]);
   else
      ShowStatus("Venter på signal");
  }

//+------------------------------------------------------------------+
void OpenTrade(ENUM_ORDER_TYPE type, double atrValue)
  {
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = (type == ORDER_TYPE_BUY) ? ask : bid;

   double slDist = atrValue * InpSLATRMult;
   double tpDist = atrValue * InpTPATRMult;
   double minDist = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(slDist < minDist)
      slDist = minDist;
   if(tpDist < minDist)
      tpDist = minDist;

   double lots = CalcLots(type, price, slDist);
   if(lots <= 0.0)
      return;

   double sl, tp;
   if(type == ORDER_TYPE_BUY)
     {
      sl = NormalizeDouble(price - slDist, _Digits);
      tp = NormalizeDouble(price + tpDist, _Digits);
      if(!trade.Buy(lots, _Symbol, price, sl, tp, "TPEA"))
         PrintFormat("Køb fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
     }
   else
     {
      sl = NormalizeDouble(price + slDist, _Digits);
      tp = NormalizeDouble(price - tpDist, _Digits);
      if(!trade.Sell(lots, _Symbol, price, sl, tp, "TPEA"))
         PrintFormat("Salg fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
     }
  }

//+------------------------------------------------------------------+
//| Lotstørrelse så et stop-loss koster InpRiskPercent af balancen   |
//+------------------------------------------------------------------+
double CalcLots(ENUM_ORDER_TYPE type, double price, double slDist)
  {
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickValue <= 0.0)
      tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0 || slDist <= 0.0)
      return 0.0;

   double lossPerLot = slDist / tickSize * tickValue;
   double riskMoney  = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   double lots = MathFloor(riskMoney / lossPerLot / step + 1e-8) * step;
   if(lots < minL)
     {
      if(minL * lossPerLot <= riskMoney * InpMaxRiskOvershoot)
         lots = minL;
      else
        {
         PrintFormat("Springer handel over: min. lot ville risikere %.2f (mål %.2f). Kontoen er for lille til dette stop.",
                     minL * lossPerLot, riskMoney);
         return 0.0;
        }
     }
   lots = MathMin(lots, maxL);

   int volDigits = (int)MathMax(0, MathCeil(-MathLog10(step)));
   lots = NormalizeDouble(lots, volDigits);

   //--- brug højst halvdelen af fri margin
   double margin = 0.0;
   if(!OrderCalcMargin(type, _Symbol, lots, price, margin) ||
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.5)
     {
      PrintFormat("Springer handel over: ikke nok fri margin (kræver %.2f)", margin);
      return 0.0;
     }
   return lots;
  }

//+------------------------------------------------------------------+
void ManageBreakeven()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsOurPosition())
         continue;

      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      if(sl <= 0.0)
         continue;

      long ptype = PositionGetInteger(POSITION_TYPE);
      if(ptype == POSITION_TYPE_BUY && sl < open)
        {
         double riskDist = open - sl;
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid - open >= riskDist * InpBreakevenR)
            trade.PositionModify(ticket, NormalizeDouble(open + 2 * _Point, _Digits), tp);
        }
      else if(ptype == POSITION_TYPE_SELL && sl > open)
        {
         double riskDist = sl - open;
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(open - ask >= riskDist * InpBreakevenR)
            trade.PositionModify(ticket, NormalizeDouble(open - 2 * _Point, _Digits), tp);
        }
     }
  }

//+------------------------------------------------------------------+
//| Ny dag: gem equity ved dagens start (overlever genstart via GV)  |
//+------------------------------------------------------------------+
void UpdateDay()
  {
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   int key = t.year * 1000 + t.day_of_year;
   if(key == g_dayKey)
      return;

   g_dayKey = key;
   string gvKey = g_gvPrefix + "day";
   string gvEq  = g_gvPrefix + "eq";
   string gvBlk = g_gvPrefix + "blocked";

   if(GlobalVariableCheck(gvKey) && (int)GlobalVariableGet(gvKey) == key && GlobalVariableCheck(gvEq))
     {
      //--- samme dag som før genstart: fortsæt med gemt startværdi
      g_dayStartEquity = GlobalVariableGet(gvEq);
      g_dayBlocked = GlobalVariableCheck(gvBlk) && GlobalVariableGet(gvBlk) > 0.5;
     }
   else
     {
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dayBlocked = false;
      GlobalVariableSet(gvKey, key);
      GlobalVariableSet(gvEq, g_dayStartEquity);
      GlobalVariableSet(gvBlk, 0.0);
     }
  }

//+------------------------------------------------------------------+
//| true = daglig tabsgrænse ramt (alt lukkes, ingen nye handler)    |
//+------------------------------------------------------------------+
bool CheckDailyLoss()
  {
   if(g_dayBlocked)
      return true;
   if(InpMaxDailyLossPct <= 0.0 || g_dayStartEquity <= 0.0)
      return false;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > g_dayStartEquity * (1.0 - InpMaxDailyLossPct / 100.0))
      return false;

   PrintFormat("Daglig tabsgrænse ramt (start %.2f, nu %.2f). Lukker alt.", g_dayStartEquity, equity);
   CloseAll();
   g_dayBlocked = true;
   GlobalVariableSet(g_gvPrefix + "blocked", 1.0);
   return true;
  }

//+------------------------------------------------------------------+
void CloseAll()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket != 0 && IsOurPosition())
         trade.PositionClose(ticket);
     }
  }

//+------------------------------------------------------------------+
//| Forudsætter at positionen er valgt (PositionGetTicket)           |
//+------------------------------------------------------------------+
bool IsOurPosition()
  {
   return PositionGetString(POSITION_SYMBOL) == _Symbol &&
          PositionGetInteger(POSITION_MAGIC) == (long)InpMagic;
  }

//+------------------------------------------------------------------+
bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket != 0 && IsOurPosition())
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
bool TradingTimeOk()
  {
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   if(t.day_of_week == 0 || t.day_of_week == 6)
      return false;
   if(InpNoFridayLate && t.day_of_week == 5 && t.hour >= 18)
      return false;
   return t.hour >= InpStartHour && t.hour < InpEndHour;
  }

//+------------------------------------------------------------------+
void ShowStatus(string status)
  {
   Comment(StringFormat("TrendPullbackEA | %s\nRisiko/handel: %.1f%%  |  Dagens start: %.2f  |  Equity: %.2f",
                        status, InpRiskPercent, g_dayStartEquity, AccountInfoDouble(ACCOUNT_EQUITY)));
  }
//+------------------------------------------------------------------+
