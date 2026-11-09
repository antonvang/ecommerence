# PAPER DASHBOARD V2 (direktørordre 59-H P2, finpudset i 59-J, Handelschart 59-K, Strategikirkegård 60-D)

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

## Handelschart (59-K)

Under bot-oversigten ligger sektionen **HANDELSCHART** (`research/tools/paper_chart.py`). Den **viser kun**
registrerede papirhandler: ingen ordreknapper, ingen handel fra grafen, ingen JavaScript. Hver graf har mærket
PAPER / SIMULATION, instrumentnavnet og bots med antal fyld.

- **Ét instrument pr. graf.** Der laves én graf pr. instrument, som FRESH-bøgerne har handlet. Flest fyld kommer
  først, og der vises højst 6. Resten står i "Ikke vist". Et rent CSS-valg (radio + `:checked`) viser én graf ad
  gangen.
- **Vindue**: fra instrumentets første fyld til cutoff, eller de seneste 7 dage, hvis forløbet er længere. Vinduet
  angives, og ældre fyld tælles som "ikke vist". Tidsaksen er i UTC, og prisaksen sidder til højre.
- **KØB** er en grøn ▲, og **SÆLG** er en rød ▼. Spidsen sidder præcis på fyldets (ts, px). Hver markør har en
  `<title>`-tooltip med tid, bot, side, qty @ px og gebyr.
- **Markedskurs**: kun hvor `observations` har `metric='mark'` for netop instrumentet (Binance USD-M premiumIndex,
  detektor k3/1). Af de viste instrumenter gælder det i dag kun BTCUSDT. Linjen brydes, hvor to punkter ligger mere
  end 3× medianafstanden fra hinanden (62 s → 3,1 min). Den interpoleres aldrig, og hvert hul er skraveret og har en
  `<title>`. BTC-mærkerne er registreret i bursts på ca. 70 min hver 2. time, så linjen har mange huller. Er der
  flere punkter end pixels, beholdes min/maks pr. pixelkolonne. Alle beholdte punkter er registrerede punkter.
- **Uden markedsserie** viser grafen kun markører uden linje og mærket "Handelspriser — ikke en markedskurs".
- **Funding-afregningspris** (`sim_funding.price` ved `settle_ts`) vises som enkeltpunkter (◇), aldrig som en kurve.
- **Spring over** vises som grå punkter i et separat bånd under prisområdet. Det sker kun, når payload har et
  `instrument` lig grafens instrument (fx `straks.skipped`). Et skip har ingen pris og står derfor ikke på prisaksen.
- **Entry (gns.)** er en stiplet vandret linje, grøn for LONG og rød for SHORT. Den kommer fra net_report's egen
  `open_qty`/`open_basis` ved cutoff og vises kun for åbne positioner. Er positionen vendt gennem nul uden at være
  flad, beholder net_report den gamle basis. Så tegnes ingen linje, og grafen siger det.
- **Equity** (`sim_equity`) læses aldrig af grafmodulet og tegnes aldrig som pris.
- Hver graf tegnes i tre SVG-størrelser (viewBox, bredde 100 %): desktop over 1000 px, tablet 601–1000 px og mobil
  op til 600 px. CSS viser den, der passer, så teksten er læsbar overalt. (V3: erstattet af én responsiv SVG, se
  nedenfor.)
- Tests: `tests/test_research_paper_chart.py` (15). De dækker ét instrument pr. SVG, markører på præcis position,
  fill-only-mærkning uden polyline, linjebrud ved et plantet hul, udtynding til registrerede punkter,
  funding-punkter, skip kun med instrument, entry kun for dokumenteret åben position, ingen equity, intet
  script/URL/knap/formular, DB byte-identisk og deterministisk output.

## Strategikirkegård (60-D)

Efter aktivitetsfeedet ligger sektionen **STRATEGIKIRKEGÅRD** (`research/tools/paper_graveyard.py`). Den viser alle
forsøg i fabriksregistret, også dem der fejlede: "Sådan ser en ærlig '99,7 % kills' ud". Labbets regel står i
introen: lås før data, holdout og kun fremad. Sektionen er kun visning. Den aktiverer intet, regner ingen nye
forskningsresultater og ændrer aldrig registret.

- **Kilde** (kun læst som bytes): `research/data/factory/registry.json` og `registry.md` samt `offdb_studies.json`,
  `migration_v1.json` og `legacy_manifest_v1.json`. Mappen kan skiftes med `--factory`.
- **Topkort**: antal forsøg og varianter, som registret selv angiver (`ledger.attempts`, `ledger.variants`), status
  fra registrets `by_status` (65 lab-eksperimenter) og brutto-alfa (`ledger.alpha_gross`). Siden tæller kun rækkerne
  for at kontrollere registrets egne tal: antal poster i `ledger.entries`, unikke id'er, seq, sum af varianter og
  alfa, sum over lineages, linjen "Attempts N, variants V, gross alpha charged A" og statustabellen i `registry.md`,
  sha256 i `registry.md` og hash-kæden (`factory.Ledger.verify`). En afvigelse vises med rødt. Den rettes ikke, og
  det store tal er stadig registrets eget.
- **Status** er registrets `status`-værdier. Forsøg uden status (amendment-17-screens, off-database-studier og
  explore0) står som "ingen status i registret" og aldrig som bestået. Findes VALIDATED ikke, siges det.
- **Tabel 1, "Forsøg i ledgeren"**: én række pr. post i `ledger.entries` i registrets rækkefølge. Antallet er lig
  `ledger.attempts`. Kolonnerne er seq, id og kilde (varianter, alfa, dato), lineage og mekanisme, status, udfald som
  registreret, omkostninger, databegrænsninger og kilde (registry.json-linje, spec-fil @commit eller studiefiler).
- **Tabel 2, "Registreret, men ikke et forsøg i ledgeren"**: lab-records, off-db-studier og amendment-17-nøgler uden
  ledgerpost samt studier i `offdb_studies.json`, som er kommet til efter registersnapshottet (de markeres og tælles
  ikke).
- **Udfald** er registrets egen tekst (`lab_state`, `evidence`, `confidence`, ledger-`note`, antal screens og
  målinger). Teksten citeres ordret, HTML-escapes og afkortes ved 200 tegn; hele teksten ligger i en tooltip. Lab-
  records har ingen begrundelsestekst i registret, og det står der. En URL i en tekst ville blive erstattet af
  "[URL udeladt]".
- **Omkostninger** vises kun, når de står direkte: en off-db-`evidence` der nævner cost (citeret), eller at specen
  har et felt med "cost" i navnet (indholdet står ikke i registret). Ellers står der "–".
- **Databegrænsninger** kommer fra `migration_v1.json` (beslutningskoder som SURVIVORSHIP_UNKNOWN, HASH_AT_ACCESS,
  LEGACY_RECORD og UNVERIFIED_ORIGIN med fuld tekst i tooltip, approval-status, "spec låst før screening",
  universstørrelse), registrets `gaps`, `legacy_manifest_v1.json` (legacy-triple) og off-db `counted_elsewhere`.
- **Filtre** for status og lineage er rent CSS (radio og `:checked`). De virker på begge tabeller og kan kombineres.
- **U3 held/multiple testing**: mærket **DIAGNOSTIC_ONLY — ingen test, ingen validering**. Stregen er
  `video_triage.luck_bar(N, 1.0)`, dvs. den forventede største z-værdi blandt N uafhængige nul-forsøg. Funktionen
  genbruges og er ikke skrevet om. N er registrets antal forsøg. Antagelsen om uafhængighed står der, og at forsøg i
  samme lineage er korrelerede, og at varianterne ikke er med i N. 1,96 vises til sammenligning. Registret har ingen
  z- eller Sharpe-værdier pr. forsøg, så siden siger "sammenligningsdata mangler" og sammenligner intet.
- Med registret 2026-11-06 (sha256 `4f2e62d5…`, matcher registry.md): 206 forsøg (146 amendment 17, 50 lab, 9
  off-database, 1 explore0), 19.438 varianter, alfa 0,399375. Status: REJECTED 47, PROPOSED 8, CLOSED 4,
  INCONCLUSIVE 3, EXTERNAL 3, ingen VALIDATED. U3: E[max z] ≈ 2,775 for N = 206. `offdb_studies.json` har ét studie
  mere end snapshottet (HFC1_OUTCOME_3D_2026-11-04, attempts 0), og siden viser det som bemærkning.
- Tests: `tests/test_research_paper_graveyard.py` (18). De dækker et syntetisk register med flere statusser og
  lineages, alle poster vist med antal lig registret, statustal lig registret, ordret og escapet tekst, U3-stregen
  med DIAGNOSTIC_ONLY og genbrug af `luck_bar`, filtre, intet script/URL/fetch/eval/knap, byte-identiske
  registerfiler, deterministisk output, flag ved afvigelse, manglende register, placering efter feedet og det rigtige
  register (antal = `ledger.attempts`, filer uændrede).

## DASHBOARD V3 (direktørordre 69 P0, 2026-11-09)

**Status: LOKAL prototype; produktionsdeploy stadig NO-GO.** Samme værktøj og kommando
(`research/tools/paper_dashboard.py`, også `--refresh` og `write_atomic`). Ingen ændring af `lab/`, `net_report.py`,
pins, protokoller, processer eller systemd. NB: timeren `copybot-dashboard.timer` kører fra denne checkout, så den
næste 5-minutters kørsel skriver V3 til `~/copybot_dashboard.html`.

Rækkefølge på siden:

1. **Header**: COPYBOT, PAPER / SIMULATION-mærket, snapshot-tid og datacutoff i UTC og en sundhedslinje:
   FRESH x / STALE y / MISSING_MARK z og samlet mærkestatus; **let DB-tjek** (`lab_qc.SCHEMA_TABLES` til stede, på
   den åbne read-only-forbindelse); fuld integritet og hashkæder køres **ikke** hvert 5. minut (lab.db er ca. 750 MB),
   så linjen siger "kør lab_qc" og viser den seneste kørsel, der er dokumenteret i `research/desk/LAB_QC.md`; og
   status for den nyeste `research/data/net_report/reconcile_*.md` (fx RECONCILED). Mangler noget, står det der.
2. **Overblik — aktuelle papirdata**: kun FRESH-konti som hovedkort. "Aktuel porteføljeværdi: Ikke tilgængelig",
   så snart én konto er STALE eller MISSING_MARK (net_report's `portfolio_current_total`). "FRESH-konti netto" er
   mærket "kun FRESH, ikke en porteføljeværdi". Et tredje kort viser datadækning (x / y konti FRESH) uden beløb.
3. **Arkiv — forældede konti** (`<details>`, lukket som standard): STALE- og MISSING_MARK-konti med equity-forløb
   (gråt), mærketid, alder, "sidst kendt, ikke aktuel" ved hvert tal og en datakvalitetslinje: antal registrerede
   `paper.mark_failed` og årsagen. For lane/carry90-konti er årsagen en **statisk note i værktøjet** (`STALE_NOTE`,
   pr. 2026-11-09: spotbenet kræver data-api.binance.vision, som lokal DNS blokerer siden ca. 2026-11-06 20:45 UTC;
   kilder MARK_FAILED_59D.md, STALE_EQUITY_59C.md, FALSIFICATION_MATRIX_ORDER61.md §3). Andre STALE-konti får "årsag
   ikke registreret her; kør lab_qc". STALE-tal er altid grå, aldrig grønne/røde og aldrig i hovedvisningen.
4. **Handelschart**: som 59-K, men nyt layout (graf + sidepanel med vindue, legende og noter) og **én responsiv SVG
   pr. graf** i stedet for tre. På smalle skærme (≤ 640 px) gør ren CSS aksetekst større, skjuler hver anden
   tidsetiket og skalerer markørerne om deres spids (`transform-box: fill-box`), så spidsen stadig sidder på
   fyldets (ts, px). Ingen JavaScript.
5. **Aktivitet**: filtrene (bot, periode, status) virker nu kun på feedet; fyld og spring over står i to kolonner
   på desktop, hver med egen rulleboks.
6. **Forskningsoversigt** (ny, `research/tools/paper_research.py`): "Ingen valideret profitabel strategi" øverst;
   kandidattabellen (§1), milepælene (§2) og blokeringerne (§3) læses fra
   `research/desk/FALSIFICATION_MATRIX_ORDER61.md`, og tillægget (direktørbeslutning 62) vises ordret over
   kandidaterne. Hvert punkt viser sin kildesti (matrixen og designnoten). Milepæle: 12/11 STRAKS, 14/11 gates,
   19/11 HFC-1 + PAR-BOG, 20/11 S1, med tid til fra cutoff. Kan tabellerne ikke parses, vises en kurateret kopi
   mærket med kilde og commit (`0f0bf50 · 2026-11-09 14:09:20 +0100`), aldrig en tom eller opdigtet status.
7. **Strategikirkegård**: uændret indhold, nye farver, lukket `<details>` som standard (opsummering: antal forsøg).
8. **Footer**: alle kilder, en read-only-erklæring og ansvarsfraskrivelsen.

**Sidestørrelse** (rigtig lab.db, 2026-11-09 ca. 16:06 UTC): V2 658.410 byte → V3 477.564 byte (−27 %).
Graf-SVG'erne faldt fra 310 KB til 111 KB. Resten er mest strategikirkegården (ca. 221 KB for alle 206 forsøg,
foldet sammen men stadig i filen), feedet (61 KB) og CSS (34 KB). Syntetisk testside: ca. 287 KB, under 400 KB-loftet
i testen.

**Tests**: ny `tests/test_research_paper_dashboard_v3.py` (11): STALE ikke i hovedvisningen men i arkivet; ingen
STALE-værdi stylet eller mærket som aktuel; porteføljeværdi ukendt ved STALE/MISSING_MARK; sundhedslinjen;
forskningsoversigt med kilder; milepæle; fallback ved manglende/ødelagt matrix; intet script/URL/fetch/eval/knap/
formular (kun `#`-ankre); DB byte-identisk og deterministisk; størrelsesloft og én SVG pr. graf; rækkefølge, lukkede
folder og responsiv CSS. To eksisterende tests er ændret, fordi forventningen bevidst er ændret:
`test_net_colours` (STALE-netto er nu `bnet old`, grå, ikke `bnet neg`) og `test_stale_never_styled_as_current`
(tjekker klassen `bnet old` og fravær af `bnet pos|neg` i stedet for V2's CSS-regel `opacity:.55`).
Desktop- og mobilvisning er kontrolleret med headless Chrome uden netværk (`unshare -rn`), 1440 og 420 px brede.

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

Filer: `research/tools/paper_dashboard.py`, `research/tools/paper_chart.py` (59-K), `research/tools/paper_graveyard.py` (60-D), `research/tools/paper_research.py` (69), `tests/test_research_paper_dashboard.py` (23 tests), `tests/test_research_paper_dashboard_v3.py` (11 tests), `tests/test_research_paper_chart.py` (15 tests) og `tests/test_research_paper_graveyard.py` (18 tests).
