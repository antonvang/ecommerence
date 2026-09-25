//+------------------------------------------------------------------+
//|                                                    NasDayEA.mq5  |
//|  Daytrading på NAS100: intradag-momentum (Gao m.fl. 2018).       |
//|                                                                  |
//|  Hver handelsdag:                                                |
//|   - Kl. 15:00 New York-tid: afkast fra gårsdagens luk til nu.    |
//|     Steget -> køb. Faldet -> sælg (short).                       |
//|   - Lukker alt kl. 15:55 New York-tid (før børsen lukker).       |
//|   - Ingen positioner natten over.                                |
//|                                                                  |
//|  Tider angives i SERVERTID. Vantage kører NY-tid + 7 timer hele  |
//|  året, så 15:00 NY = 22:00 server og 16:00 NY = 23:00 server.    |
//|  Tjek i MT5 (Market Watch-uret) og ret InpEntryHour m.fl. hvis   |
//|  din server er anderledes.                                       |
//|                                                                  |
//|  Testresultat (NAS100/US500 2019-2023): PF ca. 1,08, ca. 50 %    |
//|  vindere, tabsår forekommer. Ingen garanti. Start på demo.       |
//+------------------------------------------------------------------+
#property copyright "antonvang"
#property version   "1.00"
#property description "NAS100 intradag-momentum: én handel i sidste handelstime, lukker før luk"

#include <Trade\Trade.mqh>

input group "Tider (servertid)"
input int InpSessionCloseHour = 23; // Time hvor børsen lukker (16:00 NY = 23 server)
input int InpEntryHour        = 22; // Indgang ved starten af denne time (15:00 NY = 22)
input int InpEntryWindowMin   = 10; // Minutter efter InpEntryHour hvor indgang er tilladt
input int InpExitHour         = 22; // Luk alt fra ...
input int InpExitMinute       = 55; // ... dette minut (15:55 NY = 22:55 server)

input group "Størrelse og risiko"
input double InpExposure       = 1.0;  // Kursværdi som gange kontoen (1 = ingen gearing, maks. 10)
input double InpStopPct        = 1.0;  // Nødstop i % af kursen (0 = intet)
input double InpMinMovePct     = 0.0;  // Handl kun hvis |afkast| siden i går > dette (%)
input double InpMaxMinLotRatio = 1.5;  // Spring over hvis min. lot er større end konto x eksponering x dette
input int    InpMaxSpreadPoints = 0;   // Maks. spread i points (0 = ingen grænse)

input group "Diverse"
input ulong InpMagic = 20260927; // Magic number

CTrade trade;
int    g_tradedDayKey = -1;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpExposure <= 0.0 || InpExposure > 10.0)
     {
      Print("InpExposure skal være mellem 0 og 10");
      return INIT_PARAMETERS_INCORRECT;
     }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFillingBySymbol(_Symbol);
   if(InpExposure > 3.0)
      PrintFormat("ADVARSEL: eksponering %.1fx. Et fald på 1%% koster %.1f%% af kontoen.", InpExposure, InpExposure);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   int dayKey = t.year * 1000 + t.day_of_year;
   ulong ticket = OurPosition();

   //--- luk altid før børsen lukker (og hvis vi af en eller anden grund er over tiden)
   if(ticket != 0 && (t.hour > InpExitHour || (t.hour == InpExitHour && t.min >= InpExitMinute)))
     {
      if(trade.PositionClose(ticket))
         Print("Dagens handel lukket før lukketid");
      else
         PrintFormat("Lukning fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
     }

   if(t.day_of_week == 0 || t.day_of_week == 6)
      return;
   if(ticket != 0 || g_tradedDayKey == dayKey)
     {
      ShowStatus(ticket != 0 ? "Position åben, lukker 22:55 server" : "Dagens handel er taget");
      return;
     }
   if(t.hour != InpEntryHour || t.min >= InpEntryWindowMin)
     {
      ShowStatus(StringFormat("Venter til %02d:00 servertid", InpEntryHour));
      return;
     }

   double prevClose = PreviousSessionClose(TimeCurrent());
   if(prevClose <= 0.0)
     {
      ShowStatus("Fandt ikke gårsdagens luk");
      return;
     }
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double movePct = (bid / prevClose - 1.0) * 100.0;
   g_tradedDayKey = dayKey;  // kun ét forsøg pr. dag

   if(MathAbs(movePct) <= InpMinMovePct)
     {
      ShowStatus(StringFormat("Bevægelse %.2f%% for lille, ingen handel i dag", movePct));
      return;
     }
   if(InpMaxSpreadPoints > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPoints)
     {
      ShowStatus("Spread for høj, ingen handel i dag");
      return;
     }

   ENUM_ORDER_TYPE type = (movePct > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double price = (type == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : bid;
   double lots = CalcLots(type, price);
   if(lots <= 0.0)
      return;

   double sl = 0.0;
   if(InpStopPct > 0.0)
      sl = NormalizeDouble(type == ORDER_TYPE_BUY ? price * (1.0 - InpStopPct / 100.0)
                                                  : price * (1.0 + InpStopPct / 100.0), _Digits);
   bool ok = (type == ORDER_TYPE_BUY) ? trade.Buy(lots, _Symbol, price, sl, 0.0, "NasDay")
                                      : trade.Sell(lots, _Symbol, price, sl, 0.0, "NasDay");
   if(ok)
      PrintFormat("%s %.2f lot. Siden i går: %+.2f%%", type == ORDER_TYPE_BUY ? "Køb" : "Salg", lots, movePct);
   else
      PrintFormat("Ordre fejlede: %u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
//| Luk af den seneste H1-candle før børsens lukketid på en tidligere dag |
//+------------------------------------------------------------------+
double PreviousSessionClose(datetime now)
  {
   MqlDateTime today;
   TimeToStruct(now, today);
   for(int shift = 1; shift < 24 * 7; shift++)
     {
      datetime bt = iTime(_Symbol, PERIOD_H1, shift);
      if(bt == 0)
         return 0.0;
      MqlDateTime b;
      TimeToStruct(bt, b);
      bool earlierDay = (b.year * 1000 + b.day_of_year) < (today.year * 1000 + today.day_of_year);
      if(earlierDay && b.hour == InpSessionCloseHour - 1)
         return iClose(_Symbol, PERIOD_H1, shift);
     }
   return 0.0;
  }

//+------------------------------------------------------------------+
//| Lots så kursværdien = equity x InpExposure                      |
//+------------------------------------------------------------------+
double CalcLots(ENUM_ORDER_TYPE type, double price)
  {
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;
   double notionalPerLot = price / tickSize * tickValue;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double target = equity * InpExposure;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = MathFloor(target / notionalPerLot / step + 1e-8) * step;
   if(lots < minL)
     {
      if(minL * notionalPerLot <= target * InpMaxMinLotRatio)
         lots = minL;
      else
        {
         PrintFormat("Springer over: mindste lot har kursværdi %.2f, mål er %.2f", minL * notionalPerLot, target);
         return 0.0;
        }
     }
   lots = MathMin(lots, maxL);
   int volDigits = (int)MathMax(0, MathCeil(-MathLog10(step)));
   lots = NormalizeDouble(lots, volDigits);

   double margin = 0.0;
   if(!OrderCalcMargin(type, _Symbol, lots, price, margin) ||
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.9)
     {
      PrintFormat("Springer over: ikke nok fri margin (kræver %.2f)", margin);
      return 0.0;
     }
   return lots;
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
   Comment(StringFormat("NasDayEA | %s\nEquity: %.2f | Eksponering: %.1fx", status,
                        AccountInfoDouble(ACCOUNT_EQUITY), InpExposure));
  }
//+------------------------------------------------------------------+
