# Event farm fremadrettet: tidligere udkast er SUPERSEDED, og status for G15 og G31 (direktørordre 103)

Skrevet af Claude 2026-11-12 kl. 14:49 lokal tid. De committede filer er ikke rettet. Noten gælder i stedet.

## SUPERSEDED

| fil | status | afløst af |
|---|---|---|
| `research/desk/EVENT_FARM_FORWARD_AMENDMENT_DRAFT_100.md` | **SUPERSEDED** | `EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md` |
| `research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.md` (sha256 c914f56e…) | **SUPERSEDED**; må ikke underskrives | `EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md` (sha256 i `..._FINAL_103.sha256`) |
| `research/desk/EVENT_FARM_FORWARD_GATE_ENTRY_DRAFT_100.json` | gælder som udkast, men teksten om D5 ("PENDING_INDEPENDENT_ANCHOR") er forældet. D5 er ANCHORED (beslutning 97). Skal gennemgås, før den anvendes | – |
| `event_farm_forward.v2_plan_records` (univers 12, N 19.765) | afløst i kode af `event_farm_forward_v2.v2_final_records` (univers 96, N 19.849) | – |

**Fortsat gyldige som referencer:**
- `EVENT_FARM.md` (motor og null);
- `EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md` (filterdefinitioner og begrundelser);
- `EVENT_FARM_FORWARD_REVIEW_102.md`.

Begge de to første står med sha256 i teksten fra 103.

## Adapteren (ordre 103)

`research/tools/event_farm_source.py` (`KlineSource`, `HttpTransport`) er kun testet mod en falsk HTTP-server på
127.0.0.1. Testfilen er `tests/test_event_farm_source.py` (14 tests). Den er ikke kørt mod en rigtig vært.

**Kontrakten:**
- kun `GET /fapi/v1/klines` med symbol, interval=5m, startTime og limit 3/499 for BTCUSDT og ETHUSDT;
- 20 andre URL'er afvises i testen, herunder andre værter, ordre- og kontostier, signatur, API-nøgle og endTime;
- kildeteksten indeholder ingen anden Binance-vært og ingen nøgle-header.

**Aktivering:** uden et aktiveringsobjekt, der svarer præcis `True`, kan hverken adapteren eller transporten til den
rigtige vært oprettes. Testene viser, at intet kald sker.

**Testet fail-closed:**
- HTTP 500, timeout, nægtet forbindelse, ugyldig JSON;
- dubletter, rækker før startTime og forkert close time;
- 429 med pause uden kald;
- ikke-lukkede barer droppes; huller i svaret tælles;
- en revideret bar når bogens konfliktlog;
- ingen backfill (intet før aktiveringsslottet).

**Kald-loggen:** append-only og hash-kædet. Den fortsætter efter genstart, og en manipuleret linje afviser adapteren.

**Sammen med ForwardBookV2 i live-konfiguration** (testaktivering og loopback, 2 syntetiske døgn):
- de behandlede barer er lig børsens barer;
- alle 96 tests er lig offline;
- der er præcis ét kald pr. symbol pr. slot;
- genstart og crash giver samme bog;
- 40 slots udfald indhentes med `limit=499`;
- en bar, som børsen aldrig udgiver, bliver et hul.

**Ressourcer pr. syntetisk døgn:** 576 kald, ca. 250 KB kald-log, ca. 220 KB bog og ca. 2 s CPU.

## G15_OWNER_SIGNATURE (vurderet selvstændigt)

GATE_MATRIX (as_of 2026-11-06) siger CLOSED. Gatens krav er `owner_key_registered` og en underskrevet erklæring pr.
skabelon.
- **Nøglen:** D5 er ANCHORED (beslutning 97), så nøglekravet er opfyldt i substansen. Matricen er ikke opdateret, og
  EVENT_FARM står ikke på G15's studieliste.
- **Underskrift:** der findes ingen underskrift på teksten fra 103.
- **Status for event farm fremadrettet: CLOSED.**

## G31_EVENT_FARM_FORWARD (vurderet selvstændigt)

Gaten findes kun som udkast (`DRAFT_NOT_APPLIED`). Den er ikke i `GATE_MATRIX.json`, så handlingen er BLOCKED efter
fail-closed-reglen. **Status: CLOSED.**

| flag | status |
|---|---|
| direktørens godkendelse | nej |
| ændringen committet | nej |
| `owner_key_registered` | ja (D5 ANCHORED) |
| ejerens underskrift på 103's sha256 | nej |
| 5m-strømmen godkendt | nej |
| kode committet | motor, driver, filtre og forward v1/v2 ja; adapteren nej (ny, ikke committet) |
| loader-tests grønne | ja, kun syntetisk og loopback |
| værten svarer uden omgåelse | ukendt, intet rigtigt kald |

Intet er underskrevet, aktiveret, deployet eller kaldt mod en rigtig vært.
