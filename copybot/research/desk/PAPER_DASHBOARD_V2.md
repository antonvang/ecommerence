# PAPER DASHBOARD V2 (direktørordre 59-H P2, finpudset i 59-J)

**Status: LOKAL prototype. Produktionsdeploy: NO-GO indtil direktørgennemgang.**

## Formål

Ejeren ønsker et dashboard "ligesom i videoerne" (fx copy-trading-appen "fomo"): mørk flade, et "copy grid" af
bot-kort, et aktivitetsfeed og store grønne/røde tal. V2 giver det udseende, men forbliver ærlig: den viser kun
registrerede papirdata fra lab.db og er hele tiden mærket **PAPER / SIMULATION — ingen rigtige penge**.

## Hvad den viser, og hvorfra

- **Topkort**: "Aktuel porteføljeværdi" vises kun, når alle konti er FRESH (og der findes mindst én konto). Ellers
  står der "Ikke tilgængelig" og "N konti STALE / M MISSING_MARK". Derudover vises "FRESH-konti netto" med "x af y
  konti" og "Sidst kendt netto, STALE-konti", tydeligt mærket som ikke aktuel.
- **Copy grid**: ét kort pr. konto med navn, kilde (straks/carry90/pairs/lane), aktiv ja/nej og en statuschip
  (FRESH grøn, STALE gul "Forældet — mærket <tid> UTC, <alder> t", MISSING_MARK rød). Kortet viser også netto ved
  mærket i grøn eller rød, antal fyld, maks. fald, seneste mærke og et lille equity-forløb tegnet af de registrerede
  `sim_equity`-mærker. STALE- og MISSING_MARK-forløb er grå.
- **Tal pr. konto og summen** kommer uændret fra `research.tools.net_report.build(con, now, cutoff)` (tabellerne
  `events` lane.started/paper.started/lane.retired, `sim_equity`, `sim_fills` og `sim_funding`). Dashboardet
  regner dem ikke om.
- **Aktivitetsfeed**: de nyeste N (standard 200) registrerede hændelser til cutoff, nyeste først. Det er rækker fra
  `sim_fills` (tid, bot, instrument, køb/salg, qty @ px, gebyr) samt `events` af typerne `straks.skipped`,
  `paper.skipped`, `lane.skipped`, `paper.refused`, `paper.error`, `paper.mark_failed` og `paper.mark_recovered`
  for de viste konti, med årsag. Overskriften angiver "N nyeste af M registrerede", så en afkortning ses.
- **Filtre** for bot, periode (24 t / 7 d / alt, regnet fra cutoff) og status. De er rent HTML+CSS
  (radioknapper og `:checked`). "Alt" dækker kun de N viste rækker.

## Finpudsning (59-J)

- **Rækkefølge**: kortene står FRESH først, så STALE, så MISSING_MARK. Inden for en gruppe sorteres de efter navn,
  starttid (lane.started) og ledger-id, så rækkefølgen er stabil. Bot-filterchips følger samme rækkefølge.
- **Dubletnavne** nummereres "carry_floor #1", "carry_floor #2" osv. efter (starttid, ledger-id). Samme etiket
  bruges på kortet, filterchippen og feed-rækkerne. Ledger-id'et står stadig på kortet. Unikke navne får intet nummer.
- **Snapshot-banner** øverst: "Statisk snapshot genereret <UTC>. Kør kommandoen igen for nye tal." med kommandoen
  `python3 research/tools/paper_dashboard.py --out <fil>` og datacutoff.
- **"Sådan læses tallene"**: netto = seneste equity-mærke minus startkapital (net_report: seneste timemærke på eller
  før cutoff). FRESH = mærke højst 2 t gammelt ved cutoff. STALE = ældre, sidst kendte værdi og ikke aktuel.
  MISSING_MARK = intet mærke. Funding, gebyrer og fyld kan ligge senere end mærket. Papir-P&L uden gearing og uden
  marginmodel.
- **Feedet** viser de samme rækker som før, men delt i to sektioner: "Udførte papirhandler" (blå venstrekant) og
  "Spring over / afvisninger / fejl" (gul kant; fejl rød). Hver sektion angiver "x viste af <total> til cutoff", og
  overskriften beholder "N nyeste af M". Intet skjules.
- STALE-kort har en dæmpet netto og aldrig en grøn FRESH-chip. Ingen tal er ændret: alt kommer stadig uændret fra
  net_report.build, og en test sammenligner tallene og tidsstemplerne med 59-H-renderingen af samme syntetiske DB.

## Read-only-garantier

- lab.db åbnes kun som `file:<sti>?mode=ro` med `PRAGMA query_only=ON`. Testen bekræfter, at DB-filen er
  byte-identisk efter en kørsel, og at skrivning via værktøjets forbindelse fejler.
- Værktøjet bruger ingen netværk, ingen nye collectors, services eller daemons og ændrer intet under `lab/`.
- Outputtet er én statisk HTML-fil uden `<script>`, uden eksterne skrifttyper, billeder eller URL'er og uden
  fetch/XHR. Siden opdaterer ikke sig selv; tallene er frosset ved cutoff.
- Med fast cutoff og genereringstid (`now`) er outputtet deterministisk.

## Sådan åbnes den

```
cd /home/anton/copybot-dev/copybot
python3 research/tools/paper_dashboard.py --cutoff 2026-11-09T00:00:00Z --out /tmp/claude-1000/paper_dashboard.html
```

Åbn derefter `file:///tmp/claude-1000/paper_dashboard.html` i browseren. Uden `--cutoff` bruges tidspunktet for
kørslen. HTML med rigtige data lægges uden for repoet og committes ikke.

## Hvad der bevidst IKKE er med

Siden har ingen knapper til handel, ingen ordreindtastning, ingen wallets og ingen kontoforbindelser. Der er ingen
rigtige penge, ingen opfundne handler og ingen kunstigt opdateret P&L. Den viser aldrig grøn/sund status, når
markedsdata eller mærker mangler. Tallene er beskrivende papir-P&L uden gearing og uden marginmodel. De er ikke en
verificeret eksekverbar strategi og ikke investeringsrådgivning. Live-handel er NO-GO.

## Deploy og JS

- Deploy til produktion (web/dashboard) er blokeret, indtil direktøren har gennemgået prototypen.
- Prototypen har **ingen JavaScript**. Værten har ingen JS-motor, så hvis JS nogensinde tilføjes, er den uverificeret.
  Ejeren skal da tjekke browserkonsollen (F12) for fejl. Det gælder også nu: åbn F12 én gang og bekræft, at
  konsollen er tom.

Filer: `research/tools/paper_dashboard.py` og `tests/test_research_paper_dashboard.py` (23 tests efter 59-J).
