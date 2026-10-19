# Næste familie efter F2: sammenligningsgrundlag (2026-10-19)

Status: arbejdspapir. Ingen kode, ingen data hentet, intet afkast beregnet. En F3 kræver en dateret
protokolændring, godkendt af brugeren, før kode (PROTOCOL_V3 ændring 8 punkt 2: denne ændring kan kun køre
instrumentmodellerne `spot_perp_ratio` og `spot_delivery_ratio`).

## Udgangspunkt

- Alfa-budget (ændring 8 punkt 13): W0 = 0,05. F1 har brugt 0,0125. F2 ville bruge 0,0125. Tilbage efter F2: 0,025 = to familier.
- Programstop (punkt 15 b): 3 familier i træk uden fremad-PASS stopper programmet. F1 og F2 høster samme præmie
  (gearingsefterspørgsel); fejler begge, er to af de tre "strikes" brugt på én præmie. Næste familie bør derfor
  være økonomisk uafhængig.
- Forskningsmotoren står stille, fordi kataloget er udtømt (alle 28 skabeloner er prisforudsigende og afvist af
  ændring 8 punkt 2), og fordi scanner-fund efter protokollen ikke selv bliver til hypoteser (ændring 5 og 9).
  Det er ikke en fejl, men den betyder, at hver ny familie er det eneste, der giver ny forskning.

## Kandidater

| | A. LP-belønninger (Polymarket) | B. COIN-M/USD-M funding-spænd | C. Delta-afdækket volatilitetspræmie |
|---|---|---|---|
| Økonomisk hypotese | Market makers betales af børsens belønningspulje; belønning − adverse selection − lagerrisiko > 0 for udvalgte markeder | Samme coin finansieres forskelligt i coin- og USDT-margin; spændet betaler for et marginsegment, der ikke kan arbitrere frit | Implicit volatilitet ligger over realiseret (variansrisikopræmie); en delta-afdækket kort volatilitet høster den |
| Tag / klasse | `venue_subsidy_liquidity_rewards` / subsidy (findes, ikke kørbar) | nyt tag / carry | nyt tag / carry eller structural |
| Instrumentmodel | ny (ordrebog og belønning, ikke en kvotientserie) | ny (perp/perp i samme coin) | ny (optioner + perp-afdækning) |
| Datadækning | pm_lp-indsamleren (siden 2026-10-17, egen protokol); ingen historik før det | data.binance.vision har begge perps og funding fra 2022 (efter 2026-11-28) | Deribit DVOL er cachet; optionskurser findes ikke på data.binance.vision |
| Omkostninger | spread fanges; adverse selection og lagerrisiko er de reelle omkostninger; ingen børsgebyr | to perps × taker; spændet er lille (typisk få bp/dag) mod 2 × 0,05 % pr. vending | optionsspread og afdækningsomkostninger er store og svære at modellere uden ordrebogsdata |
| Overlap med F1/F2 | intet (anden børs, anden pengestrøm) | højt: det er stadig funding | lavt til middel (anden præmie, men samme kriseepisoder) |
| Falsifikation | pm_lp's forhåndsregistrerede porte (D-porte i PM_LP_SPEC) på holdout 2026-10-31..11-13; derefter en fremadtest | netto-spænd − omkostninger ≤ 0 på træning, eller attribution: kurs-P&L > funding-spænd | netto efter afdækning ≤ 0, eller tab i én krise > samlet præmie |
| Realistisk P(PASS) | ukendt før pm_lp's resultat [skøn umuligt nu] | lav (~0,01-0,04) [skøn] | lav, og modelrisikoen er høj [skøn] |
| Forskningsomkostning | middel: ny ændring + instrumentmodel; data findes allerede | middel: ny ændring + perp/perp-model; data efter 11-28 | høj: ny datakilde, optionsmodel, store modelvalg |
| Kan starte | efter pm_lp's resultat (efter 2026-11-27) | efter 2026-11-28 | ikke før en datakilde er afklaret |

## Anbefaling

1. **Start ingen F3 nu.** Den eneste helt uafhængige kandidat (A) afhænger af pm_lp's resultat, som først
   foreligger efter 2026-11-27. At vælge F3 før det er at bruge en af de sidste to pladser uden den vigtigste
   information.
2. **Efter 2026-11-27:** læs pm_lp's porte. Består de, skriv et udkast til en dateret ændring 10 for en
   LP-belønningsfamilie (instrumentmodel, data fra pm_lp, fremadtest som eneste afgørelse, alfa fra W0) og
   forelæg den for brugeren. Fejler de, er A død, og der er ingen stærk uafhængig kandidat; behold budgettet.
3. **B frarådes** som næste familie: den høster samme funding-præmie som F1 og ville bruge en strike på samme
   risiko.
4. **C kræver først en datakilde**, der kan håndhæves som i ændring 8 punkt 17 (kun data.binance.vision i dag).

Kvalitet frem for antal: én uafhængig, velbegrundet familie er mere værd end to korrelerede.
