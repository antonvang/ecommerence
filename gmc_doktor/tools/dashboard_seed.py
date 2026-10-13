"""Build one database document per call target for the phone dashboard (collection `stores`, doc id = domain).

Same qualification rules as call_sheet.py. Writes data/dashboard_seed/<domain>.json plus _index.json (local only:
business contact data, data/ is gitignored). Only fields Claude owns are written here; the page owns status, log,
ring_igen, kontakt, mail_sendt, opfoelg_sendt, ordre, note and grund, so re-seeding never overwrites call outcomes."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from call_sheet import SEV, load_results, qualify  # noqa: E402

# Problem-phrased headings for the customer report (the checker's titles describe the passing state).
PROBLEM = {
    "M01": "Butikken er låst med adgangskode",
    "C01": "CVR-nummeret står ikke på forsiden eller kontaktsiden",
    "C02": "Der står ingen fuld adresse på forsiden eller kontaktsiden",
    "C03": "Der står intet telefonnummer på forsiden eller kontaktsiden",
    "C04": "Der står ingen e-mailadresse på forsiden eller kontaktsiden",
    "C05": "Intet link til en kontakt- eller om os-side på forsiden",
    "P01": "Intet direkte link til returpolitik / fortrydelsesret",
    "P02": "Intet direkte link til fragt- og leveringsinfo",
    "P03": "Intet direkte link til handelsbetingelser",
    "P04": "Intet direkte link til privatlivspolitik",
    "D02": "Varer med pris 0 kr.",
    "D03": "Varer uden stregkode (GTIN/EAN)",
    "D04": "Produkttitler med salgsord eller VERSALER",
    "D05": "Varer uden billede",
    "D06": "Produkttype mangler på de fleste varer",
    "D07": "Mange førpriser med over 50 % rabat",
    "M04": "Meget få varer i butikken",
    "S01": "Produktsiderne mangler strukturerede produktdata",
    "S02": "Prisen i de strukturerede data passer ikke med den viste pris",
    "S03": "Lagerstatus i de strukturerede data passer ikke med butikken",
    "S05": "Prisen i de strukturerede data står med komma",
    "M02": "Tekst om knaphed eller nedtælling på siden",
    "M03": "Butikken bruger et myshopify.com-domæne",
    "C06": "CVR-nummeret på siden er ugyldigt",
    "D08": "Varer uden produktbeskrivelse",
    "D09": "Produktbilleder i for lav opløsning",
    "D10": "Ugyldige stregkoder (GTIN/EAN)",
    "S06": "Valutaen i de strukturerede data passer ikke med butikken",
    "P05": "Et link til en politik viser ikke politikken",
    "P06": "Returpolitikken giver under 14 dages fortrydelsesret",
    "P07": "Fragtsiden viser ingen fragtpriser",
    "M05": "Demo-tekst fra temaet står stadig på forsiden",
    "M06": "Gammelt årstal i footeren",
    "M07": "Forsiden beder Google om ikke at vise den (noindex)",
    "M08": "Butikken bruger ikke sikker forbindelse (https)",
    "D11": "Demo-varer eller fyldtekst i butikken",
    "D12": "De fleste varer er udsolgt",
    "S07": "De strukturerede produktdata mangler billede eller pris",
    "M09": "Forsiden mangler titel eller beskrivelse til Google",
    "M10": "Billeder hentes over usikker forbindelse (http)",
}
# The one example sentence read aloud on the call (follows "... fundet N ting, der kan give problemer i Google Shopping.").
# Short, plain and never stronger than what was observed: "kan", not "bliver". {ex} = a named product, if any.
SAY = {
    "C01": "Fx står jeres CVR-nummer ikke på forsiden eller kontaktsiden.",
    "C02": "Fx står der ikke en fuld adresse på forsiden eller kontaktsiden.",
    "C04": "Fx står der ikke en mailadresse på forsiden eller kontaktsiden.",
    "C05": "Fx er der ikke et link til en kontaktside på forsiden.",
    "P01": "Fx er der ikke et link til jeres returpolitik på forsiden.",
    "P02": "Fx er der ikke et link til fragt og levering på forsiden.",
    "P03": "Fx er der ikke et link til jeres handelsbetingelser på forsiden.",
    "P04": "Fx er der ikke et link til jeres privatlivspolitik på forsiden.",
    "D02": "Fx står nogle varer til 0 kr.{ex} Varer til 0 kr. kan blive afvist af Google.",
    "D05": "Fx mangler nogle varer billeder{ex} Varer uden billede kan ikke vises i Google Shopping.",
    "S02": "Fx passer prisen i jeres produktdata ikke med den pris, kunderne ser.",
    "M01": "Fx er butikken låst med en adgangskode.",
    "M03": "Fx kører butikken på et myshopify.com-domæne.",
    "M04": "Fx har butikken kun meget få varer.",
    "S05": "Fx står prisen i jeres produktdata med komma, og det kan Google læse forkert.",
    "D07": "Fx har flere varer en førpris på over det dobbelte af salgsprisen. Det kan Google se som vildledende.",
    "M02": "Fx er der tekst om knaphed eller nedtælling, som Google kan se som vildledende.",
    "D04": "Fx har nogle produkttitler salgsord eller store bogstaver, som Google kan afvise.",
    "S03": "Fx passer lagerstatus i jeres produktdata ikke med butikken.",
    "S01": "Fx mangler produktsiderne strukturerede produktdata.",
    "C06": "Fx består CVR-nummeret på jeres side ikke CVR-registrets kontrol, så det er nok skrevet forkert.",
    "D08": "Fx har nogle varer ingen beskrivelse{ex} Beskrivelse er et påkrævet felt i Google Shopping.",
    "D09": "Fx er nogle produktbilleder i lav opløsning{ex} Små billeder kan blive afvist af Google.",
    "D10": "Fx har nogle varer en stregkode, der ikke er en gyldig EAN{ex} Det kan give afviste varer i Google.",
    "S06": "Fx står priserne i jeres produktdata i en anden valuta end den, kunderne ser.",
    "P05": "Fx viser et af linkene til jeres politikker ikke politikken.",
    "P06": "Fx giver jeres returpolitik under de 14 dages fortrydelsesret, som loven kræver.",
    "P07": "Fx står der ingen fragtpriser på jeres fragtside.",
    "M05": "Fx står der stadig demo-tekst fra temaet på forsiden{ex} Det får butikken til at se ufærdig ud for Google.",
    "M07": "Fx beder jeres forside Google om ikke at vise den i søgeresultaterne. Det er et såkaldt noindex-tag.",
    "M08": "Fx kører butikken uden sikker forbindelse (https).",
    "D11": "Fx er der varer med demo- eller fyldtekst{ex} De bliver afvist, hvis de kommer med i Google-feedet.",
    "S07": "Fx mangler billede eller pris i de produktdata, Google læser i koden.",
}
DOC_ID = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")
# Large organisations/chains: unlikely to buy a 495-995 kr. fix from a cold call -> called last.
BIG = {"djoef-forlag.dk", "djoefforlag.dk", "hummel.dk", "intersport.dk", "maxizoo.dk"}
# Manual re-check overrides: speak about this finding instead of the default one, which was true but weak.
SAY_PREFER = {"andersennimbus.dk": "D05"}  # its address is on a 'Find vej' page (checked 2026-10-07)


def priority(r, fails, cwarn):
    """More observed problems first; shops with almost no products (salons, services) and big chains last."""
    p = len(fails) * 3 + len(cwarn)
    if (r.get("n_products_sampled") or 0) < 10:
        p = min(p, 1)
    if r["domain"] in BIG:
        p = 0
    return p


def say_line(fails, cwarn, prefer=None):
    """The example sentence for the most concrete finding (same order as the call sheet: problems before warnings)."""
    first = next((c for c in fails + cwarn if c["id"] == prefer), None) or next((c for c in fails + cwarn if c["id"] in SAY), None)
    if not first:
        return ""
    m = re.search(r"fx '([^']+)'", str(first["evidence"]))
    name = m.group(1).strip() if m else ""
    if len(name) > 40:
        name = name[:40].rsplit(" ", 1)[0].rstrip(" -,/") + " …"
    ex = f", blandt andet '{name}'." if name else ("" if first["id"] == "D02" else ".")
    return tidy(SAY[first["id"]].replace("{ex}", ex))


def tidy(s):
    """Customer-facing polish of checker evidence: Danish singular after 1, no stray space before a closing quote."""
    s = re.sub(r"\b1 varer\b", "1 vare", s)
    s = re.sub(r"\b1 titler\b", "1 titel", s)
    return re.sub(r"\s+'(?=[\s.,;)]|$)", "'", s)


def heading(c):
    if c["id"] == "C04" and c["status"] == "advarsel":
        return "Kontaktmailen er en gratis mailadresse (fx Gmail)"
    if c["id"] == "M07" and c["status"] == "advarsel":
        return "En produktside beder Google om ikke at vise den (noindex)"
    return PROBLEM.get(c["id"], c["title"])


def phone_parts(raw):
    """('+4531770625', '31 77 06 25') for a Danish number, else None."""
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("0045"):
        d = d[4:]
    elif d.startswith("45") and len(d) == 10:
        d = d[2:]
    if len(d) != 8:
        return None
    return "+45" + d, " ".join(d[i:i + 2] for i in range(0, 8, 2))


def build(batch_dir):
    docs = []
    for r in load_results(batch_dir):
        q = qualify(r)
        if not q or not DOC_ID.match(r["domain"]):
            continue
        fails, cwarn, _ = q
        ph = phone_parts(r["contact"]["phone"])
        if not ph:
            continue
        other = sorted([c for c in r["checks"] if c["status"] == "advarsel" and c not in cwarn], key=lambda c: SEV[c["severity"]])
        fund = [{"id": c["id"], "s": c["status"], "t": heading(c),
                 "hvad": tidy(" ".join(map(str, c["evidence"])) if isinstance(c["evidence"], list) else str(c["evidence"])),
                 "hvorfor": c["why"], "ret": c["fix"]} for c in fails + cwarn + other]
        docs.append({"butik": r["domain"], "tel": ph[0], "telefon": ph[1],
                     "email_side": (r.get("contact") or {}).get("email") or "",
                     "cvr": (r.get("contact") or {}).get("cvr") or "",
                     "prio": priority(r, fails, cwarn), "score": r.get("score"), "n_vigtige": len(fails) + len(cwarn),
                     "aabning": say_line(fails, cwarn, SAY_PREFER.get(r["domain"])), "fund": fund, "tjekket": r.get("checked_at", ""), "tjek_version": r.get("checker_version", "")})
    docs.sort(key=lambda d: (-d["prio"], d["score"] if d["score"] is not None else 100))
    seen, out = set(), []
    for d in docs:  # one business behind several domains = one call (keep the highest-priority domain)
        if d["tel"] not in seen:
            seen.add(d["tel"])
            out.append(d)
    return out


def main(batch_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    docs = build(batch_dir)
    for d in docs:
        with open(os.path.join(out_dir, d["butik"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
    with open(os.path.join(out_dir, "_index.json"), "w", encoding="utf-8") as fh:
        json.dump([d["butik"] for d in docs], fh)
    print(f"{len(docs)} butikker i {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/batch", sys.argv[2] if len(sys.argv) > 2 else "data/dashboard_seed")
