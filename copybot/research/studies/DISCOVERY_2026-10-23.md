# Discovery 2026-10-23: litteratur om funding-carry og basis (kun læsning)

Søgt 2026-10-23 ca. 18:00 lokal tid med web-søgning (3 søgninger) og én hentning af arXiv-siden nedenfor. Intet her
er en hypotese, en lås eller en afgørelse; det er kilder til de eksisterende udkast (F2 `dbasis`, F3 `fdyn`).

## Kilder

| Kilde | Type | Hovedpåstand (som kilden selv siger det) | Relevans |
|---|---|---|---|
| He, Manela, Ross, von Wachter: "Fundamentals of Perpetual Futures", [arXiv 2212.06888](https://arxiv.org/abs/2212.06888) (v7, sep. 2026) | preprint | No-arbitrage-priser for perps; afvigelser i krypto er større end i valutamarkeder og "diminish over time"; en implicit arbitragestrategi giver høje Sharpe-tal. Ifølge søgeresultatet bevæger afvigelserne sig sammen på tværs af mønter. | Høj: forklarer, hvorfor banernes forventning fra explore0 (2020–21) ligger over den funding, de får i dag |
| [arXiv 2506.08573](https://arxiv.org/pdf/2506.08573) "Designing funding rates for perpetual futures…" | preprint, teori | Funding-design (clamp) som årsag til afvigelse fra spot | Lav: ingen afkastmåling |
| [Glassnode: BTC futures annualized yield](https://studio.glassnode.com/workbench/btc-futures-annualized-yield) | dataleverandør | Perp-basis er mere volatil end kvartalskontrakternes | Middel: bekræfter F2's præmis (låst basis frem for flydende funding) |
| Robot Wealth, "The Art and Science of Trading Carry"; sharpe.ai-blog om basis | praktikere/leverandører | Funding er autokorreleret; basis 5–20 %/år, cyklisk, forsvinder i bjørnemarkeder | Lav: ikke uafhængig evidens |

## Hvad det betyder for laboratoriet

1. **Banerne (fcarry):** de taber i dag på indgangsomkostninger, fordi funding er lav (døgnrapporter 10-20–10-22:
   −203, −140, −79 USD). Litteraturen forventer netop, at afvigelserne mindskes over tid. Banernes forventning er
   explore0-tal fra 2020–21 (ændring 11 punkt 6); en z-score under forventningen er derfor ikke overraskende og er ikke
   en kodefejl. Ingen regel ændres: banerne er udforskning, og deres stopregler gælder.
2. **F1-kohorten (`fcarry:fwd202612m12`) og F3-udkastet:** afgøres af en fremadtest, ikke af 2020-tal; litteraturen er et
   argument for at læse fremadtesten, ikke backtesten. Ingen ændring.
3. **F2 `dbasis` (fra 2026-11-28):** låst basis på kvartalskontrakter er mindre afhængig af den flydende funding, som
   litteraturen siger svinder. Det støtter at teste F2 som planlagt; det beviser intet om dens afkast.
4. **Afvist som retning:** tværsnits-carry (lang høj funding / kort lav funding på tværs af mønter) er ikke afdækket i
   samme aktiv og afvises af ændring 8 punkt 2. Ikke foreslået.

## Ikke fundet

Ingen kilde i søgningen målte realiseret netto-afkast af en spot/perp-carry over en lang periode efter omkostninger.
Næste søgning (når en familie skal skrives): "funding rate autocorrelation crypto", SSRN / Journal of Futures Markets.
