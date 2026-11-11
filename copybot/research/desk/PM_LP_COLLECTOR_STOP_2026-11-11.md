# pm_lp-collectoren standset efter ejerens beslutning (2026-11-11)

Skrevet 17:35 lokal.

**Beslutning:** ejeren valgte i chatten 2026-11-11 ca. 17:34 lokal "Stop collectoren". Det er en særskilt, dateret tilladelse til at røre pm_lp (ejerens regel og G12). Ejeren oplyste samtidig, at netværksejeren bevidst har åbnet for Polymarket. Direktøren (ordre 76, 84) har stoppet Polymarket-sporet og ikke godkendt fortsat indsamling.

**Udført af Claude 16:35:07 UTC:** `systemctl --user stop pm-lp-collector.service` og `systemctl --user disable pm-lp-collector.service` (autostart fjernet). Status bagefter: inactive/dead, disabled; ingen pm_lp-proces kører. Intet andet er ændret: ingen data slettet, ingen DNS rørt, ingen kode ændret.

**Data:** `pm_lp.db` er urørt, og ingen rollback-journal ligger tilbage. Polls efter 2026-11-10 22:23 UTC bevares med tidsstempler som observationer uden for D1 (direktørbeslutning 84). D1 er stadig PASS_UNREACHABLE; afslutningsudkastet står i `PM_LP_TERMINATION_80.md`.

**Følger:**
- `lab watch` og `external_watch` vil melde pm_lp som stale. Det er korrekt og forventet.
- Holdout-reglen "collector never stopped on purpose until 11-27" er hermed tilsidesat af ejeren selv.
- Genstart kræver en ny, særskilt beslutning: `systemctl --user enable --now pm-lp-collector.service`.
