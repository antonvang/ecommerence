# VIDEO_USABLE: hvad af de 9 ejervideoer lab'et faktisk kan bruge (2026-11-09)

Grundlag:
- ordre 56 (fomo), `research/desk/fomo/`;
- ordre 57 (ORB-15), `research/desk/orb15/`;
- `VIDEO_TRIAGE_2026-11-08.md` (videoerne 1–10, TradingAgents, et TikTok-link og en LinkedIn-artikel).

| # | Brugbart element | Kilde-video | Hvad det kræver | Forslag |
|---|---|---|---|---|
| U1 | **US-åbningen som fast tidspunkt** (ORB-15 fra 09:30 ET) på QQQUSDT, fremad, beskrivende med alfa 0, brutto og netto hver for sig | Edward/NQ (ORB) | Ny datalinje: 1m-klines QQQUSDT på `fapi.binance.com` (vært allerede tilladt, kun GET). Ejer-ja til en ny stream. Tidligst første session efter 14/11 | Beskrivende måling uden alfa. Afgør intet før cirka 120 sessioner |
| U2 | **Fomo-kopi med 30 s, TP 10× og 7 t som fremadrettet falsifikation** | fomo/Grok Bot | Solana-værter, en POST-undtagelse for read-only JSON-RPC og en ny collector | Lav prioritet. Oktober-data peger allerede på FALSIFIED |
| U3 | **"Strategikirkegård" + forventet maks-Sharpe** som fast gate for alle video- og internetpåstande: Sharpe sammenlignes med det, N forsøg giver af held (Bailey og López de Prado) | @fvllport (21 DEAD, 3 beholdt, Sharpe 1,46 mod 1,16 fra held) | Intet nyt; ren metode. Lab'et har allerede Holm/BH og factory-registret | GO som standard i triage-noter (design, ingen data) |
| U4 | **Kl. 08:30 ET (US-makrodata) som hændelsestid** for TradFi-perps og BTC | "Trading er held" (nyhed kl. 14:30), Edward (7:00 CT) | BLS-kalenderen findes allerede (ændring 14). En ny hypotese kræver lås før data (pipeline 17-reglen) | Kun som kandidat til direktøren, ingen data |
| U6 | **Video→påstand→regel-pipeline** (lokal): billeder via GStreamer, et påstandsregister, en fuldstændighedstjekliste for regler (ellers NOT_REPLICABLE_FROM_VIDEO), held-tjek (U3) og opslag i lab'ets tidligere resultater (factory-registrets lineage) | @jessepbuilds | Intet netværk, ingen data. Ren lokal kode i research/desk med tests | GO-anmodning til direktøren (design + værktøj, syntetisk) |
| U5 | **LLM-agenter (TradingAgents)** | @ray_fu | API-nøgler (forbudt), nye værter og løbende udgifter | NO-GO for lab'et. Kun et designnotat om, at LLM-strategier kun kan testes fremad efter modellens vidensgrænse |

**Ikke brugbart:** videoerne 1 (dashboard uden påstand), 2 (leadgenerering), 5 (guld-"mobilbot", umulige lot-tal) og 7
(EMA-kryds; lab'et har falsificeret trendregler af den type).
