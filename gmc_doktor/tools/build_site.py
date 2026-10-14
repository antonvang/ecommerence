"""Turn the website draft into the one file to upload to the web host.

    python tools/build_site.py --ejer "Fornavn Efternavn" --adresse "Vej 1, 8000 Aarhus C"            (no CVR yet)
    python tools/build_site.py --cvr 12345678 --adresse "Vej 1, 8000 Aarhus C" [--moms]                (with CVR)
    [--mail info@webshopdoktoren.dk] [--navn Webshopdoktoren] [--domaene webshopdoktoren.dk]

Fills every placeholder in site/webshopdoktoren.html (the spans with class "ph"), adds the head a real host needs
(charset, viewport, favicon, share preview) and writes site/upload/index.html. Refuses to write a page with a
placeholder left: e-handelsloven § 7 asks for the name and geographic address of whoever sells, an e-mail, and the
CVR number once there is one. Below 50.000 kr. a year in sales a CVR number is not required, so the page then shows
"Webshopdoktoren v/ <owner>" instead."""
import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIL = "info@webshopdoktoren.dk"  # already in the page, with the copy and mail buttons
SRC = os.path.join(HERE, "..", "site", "webshopdoktoren.html")
OUT = os.path.join(HERE, "..", "site", "upload", "index.html")
PAGES = [(SRC, OUT, "/"), (os.path.join(HERE, "..", "site", "privatliv.html"), os.path.join(HERE, "..", "site", "upload", "privatliv.html"), "/privatliv")]
FAVICON = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='1' y='1' width='30' height='30' rx='8' "
           "fill='%230b6b4f'/%3E%3Cpath d='M13 8h6v5h5v6h-5v5h-6v-5H8v-6h5z' fill='%23fff'/%3E%3C/svg%3E")


def build(navn, cvr, adresse, mail, moms, domaene, ejer=""):
    for src, out, path in PAGES:
        build_page(src, out, path, navn, cvr, adresse, mail, moms, domaene, ejer)
    return os.path.abspath(os.path.dirname(OUT))


def build_page(src, out, path, navn, cvr, adresse, mail, moms, domaene, ejer):
    s = open(src, encoding="utf-8").read()
    if mail != MAIL:
        s = s.replace(MAIL, mail)
    if navn != "Webshopdoktoren":
        s = s.replace("Webshopdoktoren", navn)
    e = html.escape
    values = {"cvr": f" · CVR {e(cvr)}" if cvr else f" v/ {e(ejer)}", "adresse": e(adresse),
              "moms": "Priserne er uden moms." if moms else "Der er ingen moms på priserne, fordi virksomheden ikke er momsregistreret."}
    s = re.sub(r'<span class="ph" data-f="(\w+)">[^<]*</span>', lambda m: values[m.group(1)], s)
    if 'class="ph"' in s:
        sys.exit("Der er stadig et felt, der ikke er udfyldt.")
    cut = s.index("</style>") + len("</style>")
    head, body = s[:cut], s[cut:]
    desc = re.search(r'<meta name="description" content="([^"]*)"', head).group(1)
    org = json.dumps({"@context": "https://schema.org", "@type": "ProfessionalService", "name": navn, "url": f"https://{domaene}/",
                      "email": mail, "areaServed": "DK", "description": html.unescape(desc),
                      "address": {"@type": "PostalAddress", "streetAddress": adresse.split(",")[0].strip(),
                                  "postalCode": (re.search(r"(\d{4})", adresse.split(",")[-1]) or [None, ""])[1],
                                  "addressLocality": re.sub(r"^\s*\d{4}\s*", "", adresse.split(",")[-1]).strip(), "addressCountry": "DK"}}, ensure_ascii=False)
    extra = (f'<link rel="icon" href="{FAVICON}">\n<link rel="canonical" href="https://{domaene}{path}">\n'
             f'<meta property="og:title" content="{e(navn)}">\n<meta property="og:description" content="{desc}">\n'
             f'<meta property="og:url" content="https://{domaene}{path}">\n<meta property="og:type" content="website">\n'
             + (f'<script type="application/ld+json">{org}</script>\n' if path == "/" else ""))
    page = ('<!doctype html>\n<html lang="da">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n' + extra + head + "\n</head>\n<body>\n" + body + "\n</body>\n</html>\n")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(page)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--navn", default="Webshopdoktoren")
    ap.add_argument("--cvr", default="")
    ap.add_argument("--ejer", default="", help="ejerens fulde navn; skal med, når der ikke er CVR")
    ap.add_argument("--adresse", required=True)
    ap.add_argument("--mail", default=MAIL)
    ap.add_argument("--moms", action="store_true", help="virksomheden er momsregistreret")
    ap.add_argument("--domaene", default="webshopdoktoren.dk")
    a = ap.parse_args()
    if a.cvr and not re.fullmatch(r"\d{8}", a.cvr):
        sys.exit("CVR-nummeret skal være 8 cifre.")
    if not a.cvr and len(a.ejer.split()) < 2:
        sys.exit("Uden CVR skal ejerens fulde navn med: --ejer \"Fornavn Efternavn\".")
    if a.moms and not a.cvr:
        sys.exit("Momsregistrering kræver et CVR-nummer.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", a.mail):
        sys.exit("Mailadressen ser forkert ud.")
    print("Klar til upload:", build(a.navn, a.cvr, a.adresse, a.mail, a.moms, a.domaene, a.ejer))
