# Flyt laboratoriet fra Windows til Linux

Laboratoriets hukommelse er `data/lab/lab.db`, en hash-kædet database. Den indeholder alle resultater, godkendelser,
MVRV-observationen, skyggekontoen og politikken `autopromote`. Den ligger ikke i git, så den skal kopieres med over.

**Kun én maskine må køre laboratoriet ad gangen.** Ellers kommer der to historikker og dobbelte agenter.

## På Windows (gøres én gang)

1. Stop flåden: luk vinduet med `START_LAB.bat`, eller tryk **Stop** i dashboardet.
2. Lav en konsistent kopi:

   ```
   py -m lab export-db data/lab/lab-til-linux.db
   ```

   Kommandoen kopierer med SQLite's backup-funktion og tjekker hele hash-kæden i kopien.
3. Flyt `data/lab/lab-til-linux.db` til Linux-pc'en (USB, netværksdrev eller lignende), sammen med mapperne i
   afsnittet "Det skal også med" nedenfor.
4. Start ikke flåden på Windows igen. Den gamle paper-bot og collectoren kan køre videre; de er ikke en del af
   laboratoriet.

## På Linux

```
cd ecommerence && git pull
cd copybot
mkdir -p data/lab
cp /sti/til/lab-til-linux.db data/lab/lab.db
python3 -m lab verify
chmod +x START_LAB.sh
./START_LAB.sh
```

`python3 -m lab verify` skal melde, at kæden er hel, før flåden startes.

## Det skal også med (rettet 2026-10-18)

`lab.db` er ikke nok. Disse mapper skal med fra `data/lab/`:

| Mappe | Hvorfor |
|---|---|
| `artifacts/` | De frosne parametre (valgt variant) for hvert eksperiment. Uden dem kan paper- og skygge-agenten ikke handle (`FileNotFoundError`). |
| `reports/` | Rapporterne bag hvert resultat. |
| `market/` | Den markedsdata, laboratoriet har læst. Data-gatewayen har hashet hver fil. Hentes de igen og er de ikke byte-identiske, afvises de, så historikken kan efterprøves. |

Fra Windows over SSH (når Linux-pc'en kan nås som `anton@192.168.1.108`):

```
cd copybot/data/lab
tar -cf - artifacts reports market | ssh anton@192.168.1.108 "tar -C ~/ecommerence/copybot/data/lab -xf -"
```

## Hvad der ikke flyttes

- `data/research/pm_lp` og collectoren bliver på Windows. Laboratoriet må aldrig læse dem.
- Den gamle paper-bot (`copybot.py paper`) bliver på Windows.
- De store forskningscacher (`data/research/pmcal`, `tsmom` osv.) bruges kun af reproduktionstesten. På Linux springes den test over.
