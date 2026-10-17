# Næste runde: 3 idéer — UDKAST til din gennemlæsning (2026-10-18)

**Status.** Udkast. Intet er registreret, godkendt eller testet. Der er ikke læst kurs- eller signaldata til disse idéer.
Kun to ting er tjekket:
- **Kilderne:** slået op i Crossref.
- **Datakilderne:** at de findes, via HTTP HEAD og CoinMetrics' katalog (metadata om hvilke mønter og datoer der findes, ingen værdier).

## Det vigtigste først: held-tjekket er næsten umuligt at bestå nu

Jeg har regnet på det ud fra de registrerede forsøg:

| Hvad tælles som forsøg | Antal | Krævet årlig Sharpe i valideringen (6 mdr) for at bestå held-tjekket |
|---|---|---|
| Alle forsøg (sådan reglen er i dag) | 50 | **ca. 5,6** |
| Alle forsøg + 3 nye idéer | 56 | ca. 5,7 |
| Kun v3-forsøg (samme data og vinduer) | 16 | ca. 3,3 |

Til sammenligning:
- **Gode strategier i forskningen** har typisk en Sharpe på 1–2.
- **Vores egne 11 valideringer** lå mellem −4,6 og 4,3. Den eneste over 3 var rent markedseksponering i et rally.

Det betyder:
- **Med reglen, som den er, bliver de 3 idéer nedenfor med stor sandsynlighed afvist, uanset om de virker.** Det er
  kravet, ikke idéerne, der afgør udfaldet nu.
- **Det skyldes især for lidt data.** 6 måneders validering er for kort til at bevise en normal fordel med 95 %
  sikkerhed. Kravet stiger også, fordi forsøg på helt forskellige data (8 mønter i 2023, 30 mønter i 2023, 30 mønter i
  2022–23) regnes sammen.

### Dine valg, før vi tester (jeg ændrer intet uden din beslutning)

| Valg | Hvad det betyder | Min vurdering |
|---|---|---|
| **A. Behold reglen** | Test idéerne som de er. | Ærligt, men idéerne bliver sandsynligvis brugt op, uden at vi lærer meget. |
| **B. Fremadrettet observationstest** (anbefalet) | En idé, der består **alle andre krav**, men ikke held-tjekket, kommer på en observationsliste. Den handles simuleret på nye, usete data (fra i dag og frem) i en fast, forhåndsregistreret periode, f.eks. 6 måneder. Held-tjekket regnes så igen på de nye data. | Ingen krav sænkes. Det løser problemet med for lidt data ved at samle nyt, ægte usete data. Det koster tid. Det er stadig kun simuleret, og der er ingen rigtige penge. |
| **C. Tæl kun forsøg på samme data** | Held-tjekket tæller kun forsøg på samme vinduer og univers (v3: 16 forsøg → krav ca. 3,3). | En reel lempelse af et låst krav. Det er fagligt diskutabelt, så jeg anbefaler det ikke alene. |

## De 3 idéer

**Fælles for alle 3:**
- **Regler:** samme testregler som PROTOCOL v3.
- **Træning:** 2022-01..2023-06.
- **Validering:** 2023-07..2023-12.
- **Slut-test:** 2024 uden BTC/ETH/SOL, som allerede er set.
- **Krav og gebyrer:** de samme som før.

**Om hukommelse:** vi ved allerede, at 2022 var et bjørnemarked med stigende renter, og at slutningen af 2023 var et
rally. "Hvorfor den kunne slå købe-og-holde" er derfor delvist bagklogskab. Netop derfor er validering, held-tjek og
især nye, usete data (valg B) afgørende.

### 1. Realrente-filteret
**Kort:** hold kryptomarkedet, når de reale renter falder eller står stille, og gå ud, når de stiger.
**Hvorfor det kan virke:**
- Stigende reale renter gør fremtidige gevinster mindre værd og trækker penge ud af risikable aktiver.
- Effekten af pengepolitik på aktiekurser er veldokumenteret.

**Hvorfor den kunne slå købe-og-holde i 2022–23:**
- **2022:** de reale renter steg cirka 2,5 procentpoint, mere end i årtier, mens alts faldt cirka 70 %. Filteret ville
  have stået ude det meste af året.
- **Anden halvdel af 2023:** renterne toppede i oktober og faldt i november–december, hvor krypto steg kraftigt. Filteret
  ville have været inde i rallyet.

**Data:** FRED serie DFII10 (10-årig realrente), gratis CSV uden nøgle. Fundet (HTTP 200). En dagsværdi bruges først 2
dage efter for at undgå forsinket offentliggørelse.
**Regel:**
- Dagligt: hold alle mønter lige, hvis realrentens ændring over de sidste 20 handelsdage (variant A) eller 60 handelsdage (variant B) er ≤ 0.
- Ellers ingen position.
- Univers: de 30 v3-mønter, i slut-testen 27.

**Kilde:** Bernanke & Kuttner 2005, Journal of Finance, doi 10.1111/j.1540-6261.2005.00760.x (aktier).
**Ærlig vurdering:** den stærkeste af de tre mod købe-og-holde, fordi den er lang og går ud i dårlige perioder. Men det er
én rentecyklus, og sammenhængen mellem krypto og renter kan svækkes.

### 2. Udvanding
**Kort:** køb de mønter, hvor der udstedes færrest nye tokens, og sælg dem, hvor der udstedes flest.
**Hvorfor det kan virke:**
- Nye tokens (belønninger til validatorer, frigivelser til hold og investorer) bliver ofte solgt og giver et vedvarende salgspres.
- Hos aktier har virksomheder, der udsteder mange nye aktier, klaret sig dårligere bagefter.

**Hvorfor den kunne slå købe-og-holde i 2022–23:**
- **2022:** i et bjørnemarked uden nye købere ramte salgspresset fra udstedelser hårdest.
- **Strategiens art:** som long/short-strategi tjener den på forskellen mellem mønterne, ikke på markedets retning.
- **Svagheden:** en markedsneutral strategi slår sjældent købe-og-holde i et rally som andet halvår 2023.

**Data:** CoinMetrics community-API (gratis, uden nøgle), cirkulerende mængde (`SplyCur`). Kataloget viser dagsdata
2022–2024 for 16 af vores mønter: XRP ADA DOGE LINK LTC BCH ETC XLM UNI AAVE ALGO MANA CRV SNX BTC ETH. I slut-testen er
der 14 uden BTC/ETH.
**Regel:**
- Hver mandag: udvanding = mængdens vækst over de sidste 30 dage (variant A) eller 90 dage (variant B).
- Køb de 3 laveste, sælg de 3 højeste.

**Kilde:** Pontiff & Woodgate 2008, Journal of Finance, doi 10.1111/j.1540-6261.2008.01335.x (aktier).
**Ærlig vurdering:** stærk økonomisk logik og helt ny datatype. Men der er få mønter (16), og den har svært ved
købe-og-holde-kravet i valideringen.

### 3. Værdi på kæden (MVRV)
**Kort:** køb de mønter, hvor kursen er tættest på eller under det, ejerne i gennemsnit har betalt, og sælg dem, hvor
ejerne sidder med de største papirgevinster.
**Hvorfor det kan virke:**
- MVRV er markedsværdi ÷ "realiseret værdi", altså hvad mønterne sidst blev flyttet til.
- Høj MVRV betyder mange ejere med store gevinster, der kan tage dem hjem. Lav MVRV betyder, at sælgerne for det meste er færdige.
- Billig-mod-dyr ("value") har virket på tværs af mange markeder.

**Hvorfor den kunne slå købe-og-holde i 2022–23:**
- Sammenligningen sker på tværs af mønter, så strategien er ikke afhængig af markedets retning.
- Den har samme svaghed i rally-valideringen som idé 2.

**Data:** CoinMetrics community-API, `CapMVRVCur`, med samme 16 mønter (14 i slut-testen).
**Regel:**
- Hver mandag: køb de 3 med lavest MVRV, sælg de 3 med højest.
- Variant A: MVRV som det er. Variant B: MVRV i forhold til mønten egen gennemsnitlige MVRV over 90 dage.

**Kilde:** Asness, Moskowitz & Pedersen 2013, Journal of Finance, doi 10.1111/jofi.12021 ("value" overalt).
Desuden Campbell & Shiller 1988, Review of Financial Studies, doi 10.1093/rfs/1.3.195 (værdiforhold forudsiger afkast).
**Ærlig vurdering:** MVRV er et praktiker-mål. Den akademiske kilde handler om "value" generelt, ikke om MVRV.

## Graveyard

Ingen af de tre mekanismer er afvist før (tjekket i registret): `real_rate_timing`, `supply_dilution`,
`onchain_value_mvrv`.

## Det skal du tage stilling til

1. Valg A, B eller C for held-tjekket (min anbefaling: B).
2. Hvilke af de 3 idéer skal registreres?

Når du har valgt, skriver jeg den bindende specifikation og committer den, før der hentes data.
