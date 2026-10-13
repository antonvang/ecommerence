# GMC-Doktor (FASE 15-vinder, 7-dages test)

GMC-Doktor tjekker en Shopify-butiks offentlige sider mod Googles Merchant Center-regler (især "urigtige oplysninger") og de danske oplysningskrav til webshops. Resultatet er en dansk rapport.

- **Formål:** Første skridt i testen af, om butikker vil betale for audit eller fejlretning (`../fase15_next_project/FASE15_DECISION.md`, del F–J).
- **Krav:** Kun standardbiblioteket i Python.

## Brug

```bash
# Ét tjek
PYTHONPATH=. python -m gmcdoktor check eksempel.dk --out reports

# Mange butikker (én pr. linje) -> reports + leads.csv
PYTHONPATH=. python -m gmcdoktor batch data/to_check.txt --out data/batch

# Leadliste fra offentlige data: Common Crawl -> DNS (Shopify-IP'er) -> forside-tjek -> batch
PAGES=45 SEED=99 bash tools/pipeline.sh

# Prioriteret opkaldsliste
python tools/call_sheet.py data/batch data/opkaldsliste.csv
```

## Regler, værktøjet følger

**Kun offentlige sider:**
- forside, op til 2 kontakt-/om os-sider, `/products.json` og op til 3 produktsider med `.js`
- højst ca. 12 forespørgsler pr. butik, med 1 sekunds mellemrum

**robots.txt respekteres:**
- Shopify blokerer som standard `/policies/*`. Politikker vurderes derfor ud fra links på forsiden.
- Virksomhedsoplysninger, der måske kun står i handelsbetingelserne, rapporteres som **advarsel**, ikke fejl.

**En "fejl" er altid noget, vi faktisk har observeret.** Rapporterne bruges i telefonsamtaler med butiksejere.

**Leaddata gemmes kun lokalt** (`data/` er i `.gitignore`):
- Leaddata er virksomheders egne offentliggjorte kontaktoplysninger.
- De bruges kun til opkald efter `OUTREACH_KIT.md`: ingen kold e-mail, sms eller DM.

## Filer

| Fil | Indhold |
|---|---|
| `gmcdoktor/` | `fetch.py` (robots.txt og rate limit), `checks.py` (ca. 20 tjek), `report.py` (dansk HTML), `__main__.py` (CLI) |
| `tools/` | `collect_leads.py`, `pipeline.sh`, `call_sheet.py`, `dashboard_seed.py` (én databasepost pr. opkaldsmål til dashboardet) |
| `dashboard/opkald.html` | Opkaldsdashboard (privat artifact med database): én butik ad gangen, manuskript, svar-knapper, samtykke-log, færdige mails, ordrer og faktura. Indeholder ingen leaddata; butikkerne lægges i databasen med `dashboard_seed.py`. |
| `OUTREACH_KIT.md` | Manuskript, regler, samtykke-log, tilbud, levering og dagsmål |
| `VILKAAR_UDKAST.md` | B2B-vilkår, som den voksne aftalepart skal godkende |
| `site/index.html` | Salgsside med pladsholdere for virksomhedsoplysninger. Udgives først efter godkendelse. |
