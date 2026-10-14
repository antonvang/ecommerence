"""Build the prioritised call sheet from batch results (local data only; contains business contact data -> data/ is gitignored).

A store is a call target when it is a reachable, non-password Shopify store with a published phone number and at least
two observed problems ('fejl'), or one 'fejl' plus two warnings in identity/policies. Each row carries a one-line opener
built from the most concrete observed finding."""
import csv
import glob
import json
import os
import re
import sys

OPENER = {
    "C01": "jeres CVR-nummer ikke står på forsiden eller kontaktsiden",
    "C02": "der ikke står en fuld adresse på forsiden eller kontaktsiden",
    "C04": "der ikke står en e-mailadresse på forsiden eller kontaktsiden",
    "C05": "der ikke er et link til en kontakt- eller om os-side på forsiden",
    "P01": "der ikke er et link til jeres returpolitik på forsiden",
    "P02": "der ikke er et link til fragt- og leveringsinfo på forsiden",
    "P03": "der ikke er et link til jeres handelsbetingelser på forsiden",
    "P04": "der ikke er et link til jeres privatlivspolitik på forsiden",
    "D02": "nogle varer står med pris 0 kr.{ex}. Kommer de med i jeres Google-feed, bliver de afvist",
    "D05": "nogle varer mangler billeder{ex}, og de kan ikke vises i Google Shopping",
    "S02": "prisen i jeres strukturerede produktdata ikke passer med den viste pris",
    "M01": "butikken er låst med adgangskode",
    "M03": "butikken kører på et myshopify.com-domæne",
    "M04": "butikken kun har meget få varer",
    "S05": "prisen i jeres strukturerede produktdata står med komma (fx '349,00'), som Google kan læse forkert",
    "D07": "flere varer har en førpris på over det dobbelte af salgsprisen, som Google kan se som vildledende rabat",
    "M02": "der er tekst om knaphed eller nedtælling på siden, som Google ofte ser som vildledende",
    "D04": "nogle produkttitler indeholder salgsord eller versaler, som Google afviser",
    "S03": "lagerstatus i jeres strukturerede data ikke passer med butikken",
    "S01": "produktsiderne mangler strukturerede produktdata",
    "C06": "CVR-nummeret på jeres side ikke består CVR-registrets kontrol, så det er nok skrevet forkert",
    "D08": "nogle varer ikke har nogen beskrivelse{ex}, og beskrivelse er et påkrævet felt i Google Shopping",
    "D09": "nogle produktbilleder er i lav opløsning{ex}, og små billeder kan blive afvist af Google",
    "D10": "nogle varer har en stregkode, der ikke er en gyldig EAN{ex}, og det kan give afviste varer i Google",
    "S06": "priserne i jeres strukturerede produktdata står i en anden valuta end den, kunderne ser",
    "P05": "et af linkene til jeres politikker ikke viser politikken",
    "P06": "jeres returpolitik giver under de 14 dages fortrydelsesret, som loven kræver",
    "P07": "der ikke står nogen fragtpriser på jeres fragtside",
    "M05": "der stadig står demo-tekst fra temaet på forsiden{ex}",
    "M07": "jeres forside har et noindex-tag, der beder Google om ikke at vise den i søgeresultaterne",
    "M08": "butikken ikke bruger sikker forbindelse (https)",
    "D11": "der er varer med demo- eller fyldtekst{ex}, som bliver afvist, hvis de kommer med i Google-feedet",
    "S07": "de strukturerede produktdata mangler billede eller pris",
    "S09": "jeres stregkoder står i butikken, men kommer ikke med i de produktdata, Google læser på siden",
    "S10": "jeres produktsider har to sæt produktdata for samme vare, typisk fra både temaet og en app",
    "M11": "jeres side er sat til engelsk i koden, selvom teksten er dansk",
    "M12": "der står på forsiden, at butikken er under opbygning",
    "D15": "nogle varer har en variant til 1 krone{ex}, som ligner en fejlpris",
    "D16": "der ligger varer, der ligner kladder eller tests{ex}, synligt i butikken",
    "S12": "produktdataene på jeres side siger, at prisen er udløbet",
    "D17": "det samme billede bruges på mange forskellige varer{ex}, og det ligner et pladsholder-billede for Google",
    "S13": "jeres produktsider peger på et andet domæne som den rigtige adresse",
    "M13": "jeres robots.txt forbyder Google at læse butikken",
    "D19": "nogle produkttitler har emojis{ex}, som Googles regler for titler ikke tillader",
    "M14": "jeres side ikke er sat op til mobil, så den vises som en lille computerside på telefonen",
    "M15": "priserne på jeres side står ekskl. moms, og sælger I til private, skal de stå inkl. moms",
    "S15": "varerne hedder noget andet i jeres produktdata end i titlen, og det sammenligner Google",
    "D22": "nogle varer har en butiksintern stregkode{ex}, som Google ikke godtager som EAN",
    "D23": "den samme stregkode står på flere varianter{ex}, så Google ikke kan skelne dem",
    "D24": "nogle produkttitler er over 150 tegn{ex}, og Google skærer resten af",
    "D26": "jeres EAN-numre står i varenummer-feltet og ikke i stregkode-feltet{ex}, så Google får dem ikke",
}
# Warnings concrete enough to name on the phone (each one is something we saw, just not proven to be an error).
CONCRETE_WARN = {"S05", "D07", "M02", "D04", "S03", "S01", "D08", "D09", "P05", "S09", "S10", "M11", "M12", "D15", "D16", "S12", "D17", "D19", "M14", "M15", "S15", "D23", "D24", "D26"}
SEV = {"kritisk": 0, "høj": 1, "middel": 2, "lav": 3}


def load_results(batch_dir):
    for fp in glob.glob(os.path.join(batch_dir, "*.json")):
        try:
            yield json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue


def qualify(r):
    """(fails, concrete warnings, opener) for a call target, or None when the store does not qualify."""
    if not (r.get("reachable") and r.get("shopify")) or r.get("password"):
        return None
    phone = (r.get("contact") or {}).get("phone")
    fails = sorted([c for c in r["checks"] if c["status"] == "fejl"], key=lambda c: SEV[c["severity"]])
    cwarn = sorted([c for c in r["checks"] if c["status"] == "advarsel" and c["id"] in CONCRETE_WARN], key=lambda c: SEV[c["severity"]])
    if not phone or (len(fails) + len(cwarn)) < 2:
        return None
    concrete = [c for c in fails if c["id"] in OPENER] + [c for c in cwarn if c["id"] in OPENER]
    opener = ""
    if concrete:
        m = re.search(r"fx '([^']+)'", str(concrete[0]["evidence"]))
        ex = f" (fx '{m.group(1)[:50]}')" if m else ""
        opener = OPENER[concrete[0]["id"]].replace("{ex}", ex)
    return fails, cwarn, opener


def main(batch_dir, out_csv):
    rows = []
    for r in load_results(batch_dir):
        q = qualify(r)
        if not q:
            continue
        fails, warns, opener = q
        phone = r["contact"]["phone"]
        rows.append({"prioritet": len(fails) * 3 + len(warns), "butik": r["domain"], "telefon": phone,
                     "email_paa_siden": (r.get("contact") or {}).get("email") or "", "score": r.get("score"),
                     "fejl": len(fails), "advarsler": r.get("n_warn"), "aabning": opener,
                     "fejlliste": " | ".join([c["title"] for c in fails] + [c["title"] + " (advarsel)" for c in warns]),
                     "rapport": os.path.join(batch_dir, r["domain"] + ".html"),
                     "status": "", "samtale_med": "", "ja_til_rapport": "", "mail_samtykke": "", "tilbud": "", "betalt": "", "note": ""})
    rows.sort(key=lambda x: (-x["prioritet"], x["score"] if x["score"] is not None else 100))
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["butik"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} opkaldsmål skrevet til {out_csv}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/batch", sys.argv[2] if len(sys.argv) > 2 else "data/opkaldsliste.csv")
