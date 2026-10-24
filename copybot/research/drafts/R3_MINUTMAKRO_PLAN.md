# Plan R3: minutreaktion på makroudgivelser (BTC/ETH) — 2026-10-24 kl. 19:27, kun plan

Ændring 21k punkt 4. Ingen data hentes, intet låses, intet alfa bruges. Planen bliver en hypotese først ved en dateret
ændring før data.

## Data og lovlig start

- **Kilde:** `data.binance.vision`, USD-M månedsfiler `futures/um/monthly/klines/{BTCUSDT,ETHUSDT}/1m/…-1m-YYYY-MM.zip`,
  2020-03 … 2021-12. Det er 44 filer. Om de findes for 2020 er ikke kontrolleret: der laves ingen forespørgsel før den
  lovlige dato.
- **Lovlig start: 2026-11-14 00:00 UTC** (ændring 10b punkt 2), med banens hentevej, højst 2 samtidige downloads og
  kun explore0-måneder (læseren afviser alt andet). Ingen hentning i pm_lp's holdout (2026-10-31 … 11-13) og ingen
  2024- eller 2025+-data.
- **Kalender:** de cachede FOMC- og BLS-filer for 2020–21 (planlagte tidspunkter kendt på forhånd; FOMC 14:00 ET,
  CPI/NFP 08:30 ET). 58 udgivelser i explore0.

## Måling (forslag til den senere ændring)

- **Udgivelsestid T:** kalenderens `ts`, som altid er et helt minut.
- **Signal:** s = fortegnet af ln(C_T+1m / O_T), altså minutbaren, der starter ved T, gennemsnit af BTC og ETH.
- **Forsinkelse:** indgang ved lukkekursen for minutbaren, der starter T+2m (2 min efter udgivelsen; 1 min til at se
  baren, 1 min til eksekvering). En følsomhedsrapport med T+1m er kun beskrivende.
- **Udfald:** én låst horisont, y = s · ln(C_T+62m / C_T+2m) (60 min). Ingen horisontjagt.
- **Placebo:** samme klokkeslæt 7 døgn før (14, hvis det døgn har en kalenderbegivenhed), samme regel, som J1.
- **Klynger:** UTC-døgn (CPI og NFP falder ikke samme dag i 2020–21; ellers slås de sammen).
- **Omkostninger:** kravet efter 21i eller en senere godkendt R2-regel. Gebyr 2 × 0,040 % (2020–21) plus bog. Ved
  gulvet på 0,46 % kræver det en reaktion på næsten ½ % på 60 min efter 2 min forsinkelse, hvilket næppe findes. Derfor
  afhænger planens informationsværdi af R2.
- **Kriterier:** som 21c punkt 5 (p ≤ 0,005 tosidet, samme fortegn 2020/2021, placebo-p > 0,05, ≥ 15 klynger).
- **Look-ahead-kontrol:** minutbarens åbningstid ≥ T. Barer før T bruges kun til at kontrollere, at prisen fandtes.
- **Afvisning:** p > 0,005, fortegnsskift mellem årene, en placebo der er lige så stærk, eller en effekt under kravet.

## Risici

Få klynger (~57) giver lav styrke ved p ≤ 0,005. Macro-reaktioner kan være udtømt efter 2 min (som MISSION3 M1 og
præmiekonvergensen viste for orderflow). Et nulresultat er sandsynligt, men det ville lukke makro-sporet definitivt.
