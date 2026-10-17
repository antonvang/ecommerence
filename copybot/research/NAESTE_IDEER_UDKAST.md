# Næste runde idéer — UDKAST til din gennemlæsning

**Status:** udkast. Intet er forhåndsregistreret, godkendt eller testet. Der er ikke læst kursdata eller andre data
til disse idéer. Kun to ting er tjekket:
- **Kilderne:** alle 9 forskningsartikler er slået op i Crossref den 2026-10-17.
- **Binance-filerne:** at de findes. Tjekket med HTTP HEAD, uden at åbne indholdet.

## Hvad der stadig gælder for alle idéer

- **Regler:** samme testregler som sidst (PROTOCOL v2), og kravene ændres ikke.
- **Første test:** træning på jan–aug 2023. Strategien skal slå "bare købe og holde" efter gebyrer, og den må ikke kunne forklares som tilfældighed.
- **Anden test:** sep–dec 2023 med alle kravene.
- **Slut-test:** 2024, kun med din godkendelse. Simuleret handel også kun med din godkendelse.
- **Varianter:** hver idé har to faste varianter, som ikke ændres bagefter.
- **Mønter:** de samme 30 mønter som sidst, medmindre andet står.
- **Ærlig forventning:** de fleste idéer bliver afvist. Jo flere vi tester, jo højere bliver kravet til "ikke bare held". Det er meningen.

## Idéerne

### 1. Åben-interesse-vækst
**Kort:** køb de mønter, hvor flere og flere penge bindes i futures-kontrakter, og sælg dem, hvor pengene trækkes ud.
**Hvorfor det kan virke:** stigende "open interest" viser, at nye penge kommer ind. I råvare-futures har det forudsagt
højere afkast.
**Data:** Binance "metrics"-filer med open interest pr. 5 min (gratis, data.binance.vision, findes 2023–2024).
**Regel:** hver mandag rangeres mønterne efter ændringen i open interest-værdi over de sidste 7 (variant A) eller 28
(variant B) dage; køb top 5, sælg bund 5.
**Kilde:** Hong & Yogo 2012, Journal of Financial Economics, doi 10.1016/j.jfineco.2012.04.005.
**Min vurdering:** god og ny datatype. Kilden er råvarer, ikke krypto.

### 2. Ny penge eller short-dækning
**Kort:** en kursstigning med nye penge (open interest op) er stærkere end en stigning, hvor dem, der satsede på fald,
bare lukker (open interest ned).
**Data:** kurser + open interest (som idé 1).
**Regel:** hver mandag: score = kursafkast over 7 / 14 dage, med fortegn vendt hvis open interest faldt i samme periode;
køb top 5, sælg bund 5.
**Kilde:** Bessembinder & Seguin 1993, Journal of Financial and Quantitative Analysis, doi 10.2307/2331149 (open
interest bærer anden information end handelsvolumen).
**Min vurdering:** svagere kilde. Idéen bygger delvist på momentum, som allerede er afvist. Open interest-delen er det nye.

### 3. Smart money mod flokken
**Kort:** følg de største tradere, når de er uenige med de almindelige konti.
**Hvorfor det kan virke:** i futures har store spekulanters positioner forudsagt afkast, mens små traderes ikke har.
**Data:** Binance "metrics": long/short-forhold for top-tradere (de 20 % største konti) og for alle konti (gratis).
**Regel:** hver mandag: score = top-tradernes long/short-forhold minus alle kontoers, i gennemsnit over 7 / 14 dage; køb
top 5 (top-tradere mest optimistiske i forhold til flokken), sælg bund 5.
**Kilde:** Wang 2003, Journal of Futures Markets, doi 10.1002/fut.10056.
**Min vurdering:** den mest lovende af de nye. Det er en helt ny type data for os.

### 4. Gearings-cyklus (risikofilter)
**Kort:** når gearingen i markedet bygges hurtigere op end kurserne stiger, trækker vi os ud. Ellers holder vi markedet.
**Data:** samlet open interest for de 30 mønter + kurser.
**Regel:** dagligt: gearingsvækst = vækst i samlet open interest-værdi over 7 / 14 dage minus markedsafkastet. Ligger
den i den øverste tredjedel af de sidste 90 dage → ingen position, ellers køb alle 30 lige meget.
**Kilde:** Geanakoplos 2010, NBER Macroeconomics Annual, doi 10.1086/648285.
**Min vurdering:** et risikofilter. Det har svært ved at slå "købe og holde" i en stigende periode som efteråret 2023.

### 5. Frygtpræmie (kun BTC og ETH)
**Kort:** når optionsmarkedet forventer meget mere uro, end der faktisk har været, får man historisk betaling for at
holde risiko.
**Data:** Deribits volatilitetsindeks DVOL (gratis offentlig API, uden nøgle) + realiseret volatilitet fra vores
Binance-kurser. **Ikke tjekket endnu**, fordi tjekket ville kræve, at vi læser data. Tjekkes først ved registrering.
**Regel:** ugentligt: præmie = DVOL² − realiseret 30-dages volatilitet². Er præmien over medianen (variant A) eller i
øverste tredjedel (variant B) af de sidste 180 dage → køb BTC og ETH den næste uge, ellers ingen position.
**Kilde:** Bollerslev, Tauchen & Zhou 2009, Review of Financial Studies, doi 10.1093/rfs/hhp008.
**Min vurdering:** stærk kilde og ny datatype. Kun 2 mønter giver dog få datapunkter.

### 6. Stablecoin-tilførsel
**Kort:** når der kommer mange nye stablecoins (USDT, USDC osv.) i omløb, står der "tørt krudt" klar til at købe krypto.
**Data:** DefiLlamas samlede stablecoin-mængde pr. dag (gratis offentlig API, uden nøgle). **Ikke tjekket endnu**, af
samme grund som idé 5.
**Regel:** ugentligt: vækst i samlet stablecoin-mængde over 7 dage. Over 0 (variant A) eller over sin 90-dages median
(variant B) → køb alle 30 lige meget den næste uge, ellers ingen position.
**Kilde:** Griffin & Shams 2020, Journal of Finance, doi 10.1111/jofi.12903.
**Min vurdering:** kilden fandt effekten i 2017–18 og tolkede den som kursstøtte, ikke som ægte efterspørgsel. Det er
usikkert, om den holder.

### 7. Bitcoin-dominans-rotation
**Kort:** når Bitcoin tager en større del af markedet, går de andre mønter ofte dårligere, og omvendt.
**Data:** ægte "Bitcoin-dominans" (andel af samlet markedsværdi) findes ikke gratis med pålidelig historik. Erstatning:
Bitcoins andel af den samlede handel (dollar-volumen) blandt de 30 mønter, som vi allerede har.
**Regel:** dagligt: er Bitcoins volumenandel over de sidste 7 / 14 dage steget i forhold til perioden før → køb BTC og
sælg de 29 andre lige meget; faldet → det omvendte.
**Kilde:** ingen direkte forskningskilde. **Det er en ren hypotese**, som du selv bad om.
**Min vurdering:** svagest begrundet, og volumen er kun en erstatning for dominans.

### 8. Købspres fra takers — kræver din beslutning
**Kort:** mønter, hvor købere i en uge har handlet mere aggressivt end normalt, fortsætter op.
**Data:** "taker buy"-volumen, som allerede ligger i de Binance-kursfiler, vi har.
**Regel:** hver mandag: andel af volumen, der var aggressive køb, over 7 dage minus sit eget 60-dages gennemsnit; køb top
5, sælg bund 5. Varianter: 7 / 14 dage.
**Kilde:** Chordia & Subrahmanyam 2004, Journal of Financial Economics, doi 10.1016/S0304-405X(03)00175-2.
**Vigtigt:** en lignende idé ("ordrestrøms-ubalance" på BTC, minut-niveau) er allerede afvist. Systemet sorterer den
derfor fra automatisk, medmindre du godkender en begrundelse for, at den er væsentligt anderledes. Min begrundelse ville
være: daglig og på tværs af 30 mønter i stedet for minutter på én mønt.

## Fravalgt (og hvorfor)

- **Funding-rente-idéer:** afvist tre gange allerede.
- **Præmie/basis mellem perp og indeks:** afvist (L22 og scanner-fund).
- **Køb efter tvangslukninger:** afvist (L21).
- **"Flokken tager altid fejl" ud fra kontoernes long/short-forhold alene:** samme mekanisme som den afviste
  funding-flok-idé. Idé 3 er anderledes, fordi den sammenligner store og små tradere.

## Hvad det kræver

- **Idé 1–4:** cirka 22.000 små daglige filer fra Binance (30 mønter × 2 år). Gratis, men første download tager tid.
- **Idé 5 og 6:** to nye gratis kilder (Deribit og DefiLlama), som skal tilføjes og tjekkes.
- **Idé 7 og 8:** bruger data, vi allerede har.
- **Antal forsøg:** 8 idéer × 2 varianter = 16 nye forsøg. Kravet til "ikke bare held" stiger tilsvarende.

## Det skal du tage stilling til

1. Hvilke idéer skal med? Du kan vælge alle eller et udvalg.
2. Idé 8: skal den med, med begrundelsen ovenfor?
3. Idé 7: er volumenandel en acceptabel erstatning for Bitcoin-dominans?

Når du har valgt, skriver jeg det som en bindende specifikation og committer den, før der hentes data. Derefter
kommer koden, testene og godkendelserne, og så kører flåden.
