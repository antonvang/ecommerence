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
3. Flyt `data/lab/lab-til-linux.db` til Linux-pc'en (USB, netværksdrev eller lignende).
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

## Hvad der ikke flyttes

Markedsdata (`data/` uden for `lab.db`) hentes igen fra de offentlige kilder, når der er brug for dem. Hver læsning
bliver hashet igen af data-gatewayen. Har en fil ændret sig siden første læsning, afvises den, som den skal.
