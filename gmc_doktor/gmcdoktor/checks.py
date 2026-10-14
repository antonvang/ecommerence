"""GMC-Doktor public checks: Google Merchant Center misrepresentation signals + Danish webshop information duties.

Only public storefront pages are read: homepage, up to 2 /pages/* contact/about pages, /products.json, and up to 3
product pages with their /products/<handle>.js (same market path). robots.txt is respected, so Shopify's /policies/*
pages are NOT fetched; policies are judged by links on the homepage, and identity data that may live only in the terms
page is reported as a warning (not an error) when a terms link exists.

Design rule: a 'fejl' (error) must be something we actually observed. Anything we cannot see is 'advarsel' or skipped,
because these findings are quoted to store owners on the phone."""
import html
import json
from collections import Counter
import re
import urllib.parse
from datetime import datetime, timezone

from .fetch import Fetcher, Robots

VERSION = "0.12.1"
G = "https://support.google.com/merchants/answer/"
REF = {"misrep": G + "6150127?hl=da", "gtin": G + "160161?hl=da", "price": G + "6324371?hl=da",
       "availability": G + "6324448?hl=da", "title": G + "6324415?hl=da", "image": G + "6324350?hl=da"}
PENALTY = {"kritisk": 15, "høj": 8, "middel": 4, "lav": 2}
AREAS = ["Virksomhedsidentitet og kontakt", "Politikker", "Produktdata", "Pris og lager", "Tillid og røde flag"]

# words that say an item is not new; 'vintage' (wine years, colours) and 'genbrug' (recycled material) are left out
USED = re.compile(r"(?<!aldrig )(?<!ikke )\b(brugt|brugte|refurbished|renoveret|renoverede|istandsat|demomodel|demo-model|udstillingsmodel|udstillingsvare|second[\s-]?hand|pre-?owned|pre-?loved)\b", re.I)
# an amount of content in a title ('500 ml', '75 cl', '350 g'); container sizes and load limits are not content
QTY = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?\s*(?:g|gr|gram|kg|ml|cl|l|liter|ltr)\b(?![²³\w])", re.I)
CONTAINER = re.compile(r"(flaske|kande|glas\b|gryde|termo|krus|\bkop\b|beholder|taske|rygsæk|\bbag\b|potte|kasse|spand|balje|vase|skål|bowl|strop|dummy|lift|sæk|tank|karaffel|carafe|bottle|tumbler|thermo|\bcup\b|\bmug\b|\bjar\b|opbevaring|madkasse|drikkedunk|saddle|kapacitet|belastning|\bmax\b|dækken|gavekort|gift ?card|pocket|plantepose|krukke|urtepotte|bøjn|\brør\b|°|\d\s*mm\b)", re.I)
# a shown unit price: 'pr. kg', 'pr. 100 g', '/ l', 'kr/kg', 'per liter'
UNIT_SHOWN = re.compile(r"(pr\.?\s*(?:kg|kilo|liter|ltr|l|100\s*g|100\s*ml)\b|\d\s*(?:kr\.?|dkk)?\s*/\s*(?:kg|l|ltr|liter|100\s*g|100\s*ml)\b|per\s*(?:kg|liter|100\s*g|100\s*ml)\b)", re.I)
# return terms that break forbrugeraftaleloven: withdrawal only for unopened goods, or a period counted from the order
WITHDRAW = re.compile(r"(fortryd|retur|tilbagelever)", re.I)
UNOPENED = re.compile(r"(uåbnet|uåbnede|ubrudt|ubrudte|ikke\s+(?:være\s+)?(?:åbnet|brudt))", re.I)
# sealed hygiene/health goods may lawfully be excluded once opened; a voluntary longer return right may set its own terms
LAW_EXEMPT = re.compile(r"(forsegl|plomb|hygiejn|undertøj|badetøj|øreringe|piercing|intim|sutte|tandbørst|kontaktlins|kosmetik|software|spil\b|film|cd\b|dvd)", re.I)
LONG_RIGHT = re.compile(r"(\b(?:1[5-9]|[2-9]\d|\d{3})\s*dage|ubegrænset|livstid|fuld returret)", re.I)
HYGIENE_SHOP = re.compile(r"(protein|kosttilskud|vitamin|creme|serum|shampoo|balsam|parfume|læbe|makeup|mascara|\bvin\b|øl\b|spiritus|gin\b|whisky|kaffe|te\b|chokolade|sæbe|olie)", re.I)
FROM_ORDER = re.compile(r"(?:14|fjorten)\s*dag\w*[^.]{0,60}?\b(?:efter|fra)\s+(?:købet|købsdato\w*|købsdagen|bestilling\w*|ordredato\w*|ordren\s+(?:er\s+|blev\s+)?(?:afgivet|afsendt|sendt)|afsendelse\w*|fakturadato\w*|den\s+dag\s+(?:du|ordren)\s+(?:bestiller|bestilte|køber|købte|afgiver|afgav))", re.I)
SALES_WORDS = re.compile(r"(gratis fragt|fri fragt|\btilbud\b|\budsalg\b|spar \d+|\brabat\b|nr\.? ?1\b|!!|køb nu|free shipping|\bsale\b|bestseller)", re.I)
SCARCITY = re.compile(r"([1-9]\d* (personer|people) (kigger|ser|are viewing)|sælges hurtigt|selling fast|tilbuddet udløber|offer ends in|hurry,? only)", re.I)
TIMER_APPS = re.compile(r"(hurrify|essential-countdown|countdown-timer-bar|sales-countdown|fomo-app|stock-countdown|urgency-app)", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?:\+45[\s\-]?)?\b(?:\d{2}[\s\-]?){3}\d{2}\b")
PHONE_CTX = re.compile(r"(tlf|telefon|ring |phone|mobil|tel\.|tel:)", re.I)
CVR = re.compile(r"(?:CVR|CVR[\-\s]?nr\.?|CVR[\-\s]?nummer|VAT(?:[\-\s]?(?:no|nr|number))?\.?|Org\.?\s?nr\.?)\s*[:.\-]?\s*(?:DK[\s\-]?)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})\b", re.I)
STREET = re.compile(r"\b[A-ZÆØÅ][a-zæøåA-ZÆØÅ\.\-]*(?:vej|gade|allé|alle|stræde|torv|plads|vænge|parken|bakke|boulevard|have|toften|marken)(?:en|et|e)?\s?\d+[A-Za-z]?", re.I)
POSTCODE_CITY = re.compile(r"\b(?:DK[\-\s]?)?([1-9]\d{3})\s+([A-ZÆØÅ][a-zæøå]+(?:[\s\-][A-ZÆØÅ]?[a-zæøå]+)?)")

POLICY_KEYS = {
    "returns": (r"/policies/refund-policy", r"(retur|fortryd|refund|return|ombyt)"),
    "shipping": (r"/policies/shipping-policy", r"(fragt|levering|forsendelse|shipping|delivery)"),
    "terms": (r"/policies/terms-of-service", r"(handelsbetingelser|betingelser|vilk[aå]r|terms)"),
    "privacy": (r"/policies/privacy-policy", r"(privatliv|persondata|privacy)"),
}
HELP_LINK = re.compile(r"(faq|hjælp|help|kundeservice|customer service|support|spørgsmål)", re.I)
FREE_MAIL = ("gmail.", "hotmail.", "outlook.", "yahoo.", "live.", "icloud.")
JUNK_MAIL = ("example.", "sentry", "wixpress", "domain.", "email.com", "@2x", ".png", ".jpg", ".webp", "shopify")


# Theme demo text that is still on the homepage (Shopify Dawn and other free themes ship these as section defaults).
DEMO = re.compile(r"(talk about your brand|share information about your brand with your customers|pair text with an image to focus on|"
                  r"use this text to share information about your brand|add a tagline|lorem ipsum|example product title|"
                  r"your content goes here|fortæl om dit brand|del oplysninger om dit brand med dine kunder|kombiner tekst med et billede|eksempel på produkttitel)", re.I)
COPYRIGHT = re.compile(r"(?:©|copyright)\s*(?:20\d{2}\s*[-–]\s*)?(20\d{2})", re.I)
DAYS = re.compile(r"(\d{1,3})\s*(?:dage|dages|days|hverdage)", re.I)
RETURN_CTX = re.compile(r"(retur|fortryd|return|ombyt|withdraw)", re.I)
MONEY_CTX = re.compile(r"(refunder|tilbagebetal|beløb|pengene|levering|leveret|afsend|svar|behandl|refund)", re.I)
LONG_RETURN = re.compile(r"\b(?:1[4-9]|[2-9]\d|\d{3})\s*(?:dage|dages|days|hverdage)|fjorten|to uger|\b\d+\s*(?:uger|måned|weeks|months)", re.I)
META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
DEMO_PRODUCT = re.compile(r"(lorem ipsum|this is a demo|dette er en demo|example product|eksempel på produkt)", re.I)
GENERIC_TITLE = re.compile(r"\s*(home|forside|hjem|my store|min butik|welcome|velkommen|shop|webshop)?\s*", re.I)
HTTP_IMG = re.compile(r"""<img\b[^>]*\ssrc=["']http://[^"']+""", re.I)
PRICE_TITLE = re.compile(r"\d+\s?(?:kr\.?|,-)(?![\wæøå])", re.I)
GIFT = re.compile(r"(gavekort|gift ?card)", re.I)
EX_VAT = re.compile(r"(ekskl\.?\s*moms|eksklusiv(?:e)?\s+moms|ex\.?\s*moms|excl\.?\s*(?:vat|moms)|priser(?:ne)? er uden moms)", re.I)
PREORDER = re.compile(r"(pre-?order|forudbestil)", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u2705\u274C]")
DRAFT = re.compile(r"^\s*(copy of|kopi af|testprodukt|test product|testvare|do not (?:buy|use)|ikke køb|fejloprettelse|placeholder)\b|^\s*test\s*\d*\s*$", re.I)
SAMPLE = re.compile(r"(prøve|sample|tester|vareprøve|gavekort|gift ?card|stof ?prøve|farveprøve)", re.I)
UNDER = re.compile(r"(under construction|under opbygning|åbner snart|opening soon|website coming soon|webshoppen åbner)", re.I)
HTML_LANG = re.compile(r"""<html\b[^>]*\slang=["']?([A-Za-z-]+)""", re.I)
DA_WORDS = {"og", "til", "med", "på", "er", "det", "vi", "af", "din", "dine", "jeres", "kurv", "levering", "fragt", "køb", "varer", "ikke", "eller"}
EN_WORDS = {"the", "and", "with", "your", "you", "our", "shipping", "cart", "buy", "products", "not", "or"}


def noindex(h):
    """The meta robots tag of the page, if it tells search engines not to index it."""
    for m in META_TAG.finditer((h or "")[:200_000]):
        t = m.group(0)
        if re.search(r'name=["\']?(?:robots|googlebot)\b', t, re.I) and re.search(r'content=["\'][^"\']*noindex', t, re.I):
            return t[:120]
    return None
SHIP_PRICE = re.compile(r"(\d+[.,]?\d*\s*(?:kr\b|kr\.|dkk|,-)|gratis|fri fragt|free shipping|\bkr\.?\s*\d)", re.I)


def gtin_reserved(code):
    """True for a GTIN in a range kept for in-store use (prefix 2, 02 or 04), which Google does not accept."""
    d = re.sub(r"\s", "", str(code))
    if len(d) == 8:
        return d[0] == "2"
    if len(d) == 14:
        d = d[1:]  # drop the packaging indicator
    d = d.zfill(13)
    return d[0] == "2" or d[:2] in ("02", "04")


def gtin_ok(code):
    """True for a GTIN-8/12/13/14 with a correct check digit."""
    d = re.sub(r"\s", "", str(code))
    if not d.isdigit() or len(d) not in (8, 12, 13, 14):
        return False
    body = [int(c) for c in d[:-1]][::-1]
    total = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(body))
    return (10 - total % 10) % 10 == int(d[-1])


def cvr_ok(digits):
    """Danish CVR numbers pass a modulus-11 check with weights 2,7,6,5,4,3,2,1."""
    if not re.fullmatch(r"\d{8}", digits or ""):
        return False
    return sum(int(c) * w for c, w in zip(digits, (2, 7, 6, 5, 4, 3, 2, 1))) % 11 == 0


def _base(title):
    """The first two words of a title, before any ' - ', ',' or '(' and without numbers: colours, sizes, years and model
    numbers of one product share them, different products rarely do."""
    t = (title or "").lower()
    head = re.split(r"\s[-–|]\s|,|\(", t)[0]
    words = [w for w in re.findall(r"\w+", head) if not re.search(r"\d", w) and len(w) > 1]
    return " ".join(words[:2]) or t.strip()


def _site(url):
    """The registrable part of a URL's host (shop.x.dk and www.x.dk are the same site)."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return ".".join(host.split(".")[-2:])


def _main_text(h):
    """Text of the page's <main> (falls back to the whole page), without the theme's header and footer."""
    m = re.search(r"<main\b[^>]*>(.*?)</main>", h or "", re.S | re.I)
    return _text(m.group(1) if m else h)


def _text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", h or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _links(h):
    return [(html.unescape(m.group(1)), _text(m.group(2)))
            for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', h or "", re.S | re.I)]


def _ldjson(h):
    out = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', h or "", re.S | re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if "@graph" in x:
                    stack.extend(x["@graph"] if isinstance(x["@graph"], list) else [x["@graph"]])
                out.append(x)
            elif isinstance(x, list):
                stack.extend(x)
    return out


def _check(cid, area, sev, title, status, evidence, why, fix, ref=None):
    return {"id": cid, "area": area, "severity": sev, "title": title, "status": status, "evidence": evidence,
            "why": why, "fix": fix, "ref": ref}


def _num(x):
    """Parse a price that may use Danish formatting ('1.299,00', '349,00') or schema.org formatting ('349.00')."""
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^\d,.\-]", "", str(x))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _offers(items):
    offers = []
    for it in items:
        o = it.get("offers") or []
        offers.extend(o if isinstance(o, list) else [o])
        for hv in it.get("hasVariant", []) or []:
            ov = hv.get("offers") or []
            offers.extend(ov if isinstance(ov, list) else [ov])
    return [o for o in offers if isinstance(o, dict)]


def run(domain, max_products_pages=5):
    f = Fetcher(domain, max_requests=24)
    res = {"domain": f.domain, "checker_version": VERSION, "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "shopify": False, "reachable": False, "password": False, "contact": {}, "checks": [], "notes": []}
    C = res["checks"]
    st, final, hdr, home = f.get("/")
    if st != 200:
        res["notes"].append(f"Forsiden kunne ikke hentes (status {st}).")
        res.update(score=None, counts={}, n_fail=0, n_warn=0, fetch_log=f.log)
        return res
    res["reachable"] = True
    hl = {k.lower(): v for k, v in hdr.items()}
    res["shopify"] = bool(hl.get("x-shopid") or "shopify" in (hl.get("powered-by", "") + hl.get("server", "")).lower()
                          or "cdn.shopify.com" in home or "Shopify.theme" in home or "/cdn/shop/" in home)
    res["password"] = "/password" in final or "template-password" in home
    res["final_url"] = final
    links = _links(home)
    home_txt = _text(home)
    hrefs = " ".join((re.sub(r"^https?://[^/]+", "", h) + " " + l) for h, l in links)
    labels = " ".join(l for _, l in links)

    # ---------- contact / about pages (allowed by Shopify robots) ----------
    page_txt, pages_seen, cand = "", [], []
    for href, label in links:
        p = re.sub(r"^https?://[^/]+", "", href)
        if "/pages/" in p and (re.search(r"(kontakt|contact|kundeservice|customer-service|om-os|omos|om-mig|om-butikken|about|hvem|virksomhed|impressum|info)", p + " " + label, re.I)
                               or re.search(r"/pages/om(?:[-?]|$)", p) or re.fullmatch(r"\s*om( os| mig| butikken)?\s*", label, re.I)):
            p = p.split("?")[0]
            if p not in cand:
                cand.append(p)
    for p in cand[:2] or ["/pages/kontakt", "/pages/contact"]:
        s2, _, _, b2 = f.get(p)
        if s2 == 200:
            page_txt += " " + _text(b2)
            pages_seen.append(p)
    all_txt = home_txt + " " + page_txt

    # ---------- policies via homepage links ----------
    pol_found, pol_pages = {}, {}
    for k, (pol, kw) in POLICY_KEYS.items():
        m = re.search(pol, hrefs) or re.search(r"/pages/\S*" + kw, hrefs, re.I) or re.search(kw, labels, re.I)
        pol_found[k] = m.group(0)[:80] if m else None
        for href, label in links:  # a policy that lives on a normal /pages/ page can be read (robots allows it)
            path = re.sub(r"^https?://[^/]+", "", href).split("?")[0]
            if path.startswith("/pages/") and (re.search(kw, label, re.I) or re.search(kw, path, re.I)) and path not in pages_seen:
                pol_pages[k] = (path, label.strip() or path)
                break
    has_terms = bool(pol_found["terms"])

    # ---------- products.json + product pages + .js (same market path) ----------
    products = []
    s3, _, _, pj = f.get("/products.json?limit=250")
    if s3 == 200:
        try:
            products = json.loads(pj).get("products", [])
        except Exception:
            products = []
    res["n_products_sampled"] = len(products)
    pp = []
    # spread the sample over the whole catalogue instead of only the newest products
    step = max(1, len(products) // max_products_pages) if products else 1
    for prod in products[::step][:max_products_pages]:
        h = prod.get("handle")
        if not h:
            continue
        s4, final4, _, b4 = f.get(f"/products/{h}")
        if s4 != 200:
            continue
        js = None
        js_path = urllib.parse.urlsplit(final4).path.rstrip("/") + ".js"
        s5, _, _, b5 = f.get(js_path)
        if s5 == 200:
            try:
                js = json.loads(b5)
            except Exception:
                js = None
        pp.append((prod, b4, js))

    A0, A1, A2, A3, A4 = AREAS
    if res["password"]:
        C.append(_check("M01", A4, "kritisk", "Butikken er låst med adgangskode", "fejl", final,
                        "Google kan ikke gennemgå en låst butik, så produkterne kan ikke godkendes.",
                        "Fjern adgangskoden under Onlinebutik → Præferencer, når butikken er klar.", REF["misrep"]))

    # ---------- identity & contact ----------
    where = "forsiden og kontakt-/om os-siden" if pages_seen else "forsiden"
    not_seen = "advarsel" if has_terms else "fejl"
    hint = " Det kan stå i handelsbetingelserne, som vi ikke læser." if has_terms else ""
    cvr = CVR.search(all_txt)
    C.append(_check("C01", A0, "kritisk", "CVR-nummer er synligt", "ok" if cvr else not_seen,
                    cvr.group(0) if cvr else f"Ikke fundet på {where}.{hint}",
                    "Manglende virksomhedsoplysninger er det hyppigste fund hos suspenderede butikker (Googles regel om urigtige oplysninger). Dansk lov kræver også, at webshops oplyser CVR-nummer.",
                    "Skriv firmanavn og CVR-nummer i footeren på alle sider, fx 'Firmanavn ApS · CVR 12345678'.", REF["misrep"]))
    addr = None
    for sm in STREET.finditer(all_txt):
        pcm = POSTCODE_CITY.search(all_txt[sm.end(): sm.end() + 80])
        if pcm:
            addr = sm.group(0) + ", " + pcm.group(0)
            break
    C.append(_check("C02", A0, "kritisk", "Fysisk adresse er synlig", "ok" if addr else not_seen,
                    addr or f"Ingen fuld adresse (vej, nr., postnr. og by) fundet på {where}.{hint}",
                    "En fysisk adresse er et af de vigtigste tillidssignaler for Google, og den er lovpligtig for danske webshops.",
                    "Skriv fuld adresse i footeren og på kontaktsiden.", REF["misrep"]))
    mails = [m.group(0) for m in EMAIL.finditer(all_txt) if not any(j in m.group(0).lower() for j in JUNK_MAIL)]
    mail = mails[0] if mails else None
    free = bool(mail and mail.split("@")[1].lower().startswith(FREE_MAIL))
    C.append(_check("C04", A0, "høj", "E-mailadresse er synlig", ("advarsel" if free else "ok") if mail else not_seen,
                    (mail + (" (gratis mailudbyder)" if free else "")) if mail else f"Ingen e-mailadresse fundet på {where}.{hint}",
                    "En synlig e-mail er lovpligtig og et tillidssignal. En adresse på eget domæne virker mere troværdig end Gmail/Hotmail.",
                    "Vis en e-mail på butikkens eget domæne, fx kontakt@dinbutik.dk, i footeren og på kontaktsiden.", REF["misrep"]))
    cvr_digits = re.sub(r"\D", "", cvr.group(1)) if cvr else None
    all_cvr = sorted({re.sub(r"\D", "", m.group(1)) for m in CVR.finditer(all_txt) if re.search(r"CVR", m.group(0), re.I)})
    if len(all_cvr) >= 2:
        C.append(_check("C07", A0, "lav", "Siden viser ét CVR-nummer", "advarsel", f"Siden viser {len(all_cvr)} forskellige CVR-numre: {', '.join(all_cvr[:3])}.",
                        "Med flere CVR-numre er det uklart for kunder og Google, hvilken virksomhed der sælger varen.",
                        "Vis kun CVR-nummeret på den virksomhed, der sælger, eller forklar tydeligt, hvem der er hvem.", REF["misrep"]))
    if cvr and re.search(r"CVR", cvr.group(0), re.I) and not cvr_ok(cvr_digits):
        C.append(_check("C06", A0, "høj", "CVR-nummeret er gyldigt", "fejl", f"fx '{cvr.group(0).strip()}' består ikke CVR-registrets kontrol.",
                        "Et forkert CVR-nummer gør, at hverken Google eller kunderne kan slå virksomheden op, og det ligner urigtige oplysninger.",
                        "Ret CVR-nummeret, så det passer med virk.dk (8 cifre).", REF["misrep"]))
    phones = []
    for m in PHONE.finditer(all_txt):
        s = m.group(0).strip()
        if cvr_digits and re.sub(r"\D", "", s)[-8:] == cvr_digits:
            continue
        if s.startswith("+45") or PHONE_CTX.search(all_txt[max(0, m.start() - 40): m.start()]):
            phones.append(s)
    phone = phones[0] if phones else None
    C.append(_check("C03", A0, "middel", "Telefonnummer er synligt", "ok" if phone else "advarsel", phone or f"Intet telefonnummer fundet på {where}.",
                    "Google lægger vægt på, at kunder kan kontakte butikken på flere måder. Et telefonnummer øger tilliden.",
                    "Vis et telefonnummer i footeren eller på kontaktsiden.", REF["misrep"]))
    C.append(_check("C05", A0, "middel", "Kontakt- eller om os-side findes", "ok" if pages_seen else "fejl",
                    ", ".join(pages_seen) or "Ingen kontakt- eller om os-side fundet via forsidens links.",
                    "Google kigger efter en tydelig side om, hvem der står bag butikken.",
                    "Lav en side med virksomhedsnavn, adresse, CVR, telefon og e-mail, og link til den fra menu og footer.", REF["misrep"]))
    res["contact"] = {"cvr": cvr_digits, "phone": phone, "email": mail}

    # ---------- policies ----------
    sev = {"returns": "kritisk", "shipping": "høj", "terms": "høj", "privacy": "middel"}
    names = {"returns": ("P01", "Link til returpolitik / fortrydelsesret"), "shipping": ("P02", "Link til fragt- og leveringsinfo"),
             "terms": ("P03", "Link til handelsbetingelser"), "privacy": ("P04", "Link til privatlivspolitik")}
    fixes = {"returns": "Udfyld returpolitikken (Indstillinger → Politikker) med 14 dages fortrydelsesret, hvem der betaler returfragt og hvordan man returnerer, og link til den i footeren.",
             "shipping": "Skriv fragtpriser og leveringstid i en fragtpolitik, og link til den i footeren. Fragtprisen skal svare til fragtindstillingerne i Merchant Center.",
             "terms": "Tilføj handelsbetingelser med virksomhedsoplysninger, betaling, levering, fortrydelsesret og reklamation, og link til dem i footeren.",
             "privacy": "Tilføj en privatlivspolitik og link til den i footeren."}
    help_link = HELP_LINK.search(labels)
    for k in POLICY_KEYS:
        cid, title = names[k]
        if pol_found[k]:
            status, ev = "ok", pol_found[k]
        elif k in ("returns", "shipping") and has_terms:
            status, ev = "advarsel", f"Intet direkte link; oplysningerne står måske i handelsbetingelserne ({pol_found['terms']}). Google og kunder skal kunne finde dem let."
        elif help_link:
            status, ev = "advarsel", f"Intet direkte link; kun '{help_link.group(0)}'-link fundet, hvor oplysningerne måske står."
        else:
            status, ev = "fejl", "Intet link fundet på forsiden."
        C.append(_check(cid, A1, sev[k], title, status, ev,
                        "Manglende eller svært tilgængelige politikker er en af de hyppigste årsager til suspendering for 'urigtige oplysninger'.",
                        fixes[k], REF["misrep"]))

    # ---------- product data ----------
    if s3 == "robots":
        res["notes"].append("products.json er blokeret af robots.txt, så produktdata er ikke tjekket.")
    elif not products:
        res["notes"].append(f"products.json gav ingen produkter (status {s3}), så produktdata er ikke tjekket.")
    else:
        zero = [p["title"] for p in products if any(float(v.get("price") or 0) == 0 for v in p.get("variants", []))]
        C.append(_check("D02", A2, "høj", "Ingen varer med pris 0", "fejl" if zero else "ok",
                        f"{len(zero)} varer med pris 0, fx '{zero[0][:60]}'" if zero else f"{len(products)} varer tjekket.",
                        "Varer med pris 0 afvises og kan ligne vildledning.", "Sæt en rigtig pris, eller fjern varen fra Google-kanalen.", REF["price"]))
        bad_titles = [p["title"] for p in products if len(p.get("title", "")) > 150
                      or (p.get("title", "").isupper() and len(p.get("title", "")) > 8) or SALES_WORDS.search(p.get("title", ""))
                      or (PRICE_TITLE.search(p.get("title", "")) and not GIFT.search(p.get("title", "")))]
        C.append(_check("D04", A2, "middel", "Produkttitler uden salgsord eller VERSALER", "advarsel" if bad_titles else "ok",
                        f"{len(bad_titles)} titler, fx '{bad_titles[0][:70]}'" if bad_titles else "Ingen problematiske titler fundet.",
                        "Google afviser titler med salgsbudskaber (fx 'gratis fragt', 'tilbud') og bruger titlen til at matche søgninger.",
                        "Skriv titler som 'Mærke + produkttype + egenskab (farve/størrelse/materiale)', uden salgsord.", REF["title"]))
        noimg = [p["title"] for p in products if not p.get("images")]
        C.append(_check("D05", A2, "høj", "Alle varer har billeder", "fejl" if noimg else "ok",
                        f"{len(noimg)} varer uden billede, fx '{noimg[0][:60]}'" if noimg else "Alle tjekkede varer har billeder.",
                        "Varer uden billede kan ikke vises i Google Shopping.", "Tilføj mindst ét tydeligt produktbillede.", REF["image"]))
        notype = [p for p in products if not (p.get("product_type") or "").strip()]
        C.append(_check("D06", A2, "lav", "Produkttype er udfyldt", "advarsel" if len(notype) > len(products) / 2 else "ok",
                        f"{len(notype)} af {len(products)} varer mangler produkttype.",
                        "Produkttypen hjælper Google med at kategorisere varen og målrette annoncer.",
                        "Udfyld 'Produkttype' på varerne (fx 'Plaid', 'Kokkekniv').", REF["title"]))
        big = []
        for p in products:
            for v in p.get("variants", []):
                try:
                    pr, cp = float(v.get("price") or 0), float(v.get("compare_at_price") or 0)
                except ValueError:
                    continue
                if pr > 0 and cp > 2 * pr:
                    big.append(p["title"])
                    break
        C.append(_check("D07", A2, "middel", "Ingen urealistiske førpriser (over 50 % rabat)", "advarsel" if len(big) >= 3 else "ok",
                        f"{len(big)} varer med førpris over 2× salgspris, fx '{big[0][:60]}'" if big else "Ingen ekstreme førpriser fundet.",
                        "Kunstigt høje førpriser er et kendt tegn på vildledning. Danske regler kræver desuden, at en førpris er den laveste pris de seneste 30 dage.",
                        "Fjern 'sammenlign ved'-priser, der ikke er reelle tidligere priser.", REF["misrep"]))
        nodesc = [p["title"] for p in products if len(_text(p.get("body_html") or "")) < 20]
        if nodesc:
            many = len(nodesc) >= 3 or len(nodesc) >= len(products) * 0.1
            C.append(_check("D08", A2, "høj", "Alle varer har en beskrivelse", "fejl" if many else "advarsel",
                            f"{len(nodesc)} af {len(products)} varer har ingen beskrivelse, fx '{nodesc[0][:60]}'",
                            "Beskrivelse er et påkrævet felt i Google Shopping. Varer uden beskrivelse kan blive afvist, og de matcher færre søgninger.",
                            "Skriv 2-4 sætninger om varen: hvad det er, materiale, mål og hvad den bruges til.", REF["title"]))
        tiny, small = [], []
        for prod in products:
            im = (prod.get("images") or [None])[0]
            if not isinstance(im, dict) or not im.get("width") or not im.get("height"):
                continue
            side = min(int(im["width"]), int(im["height"]))
            if side < 100:
                tiny.append(prod["title"])
            elif side < 500:
                small.append(prod["title"])
        if tiny or len(small) >= 3:
            C.append(_check("D09", A2, "høj" if tiny else "middel", "Produktbilleder har høj nok opløsning", "fejl" if tiny else "advarsel",
                            f"{len(tiny)} varer har et hovedbillede under 100 px, fx '{tiny[0][:60]}'" if tiny
                            else f"{len(small)} varer har et hovedbillede under 500 px, fx '{small[0][:60]}'",
                            "Google afviser billeder under 100 × 100 px (250 × 250 px for tøj) og anbefaler mindst 800 px, så varen kan vises skarpt.",
                            "Upload produktbilleder på mindst 800 × 800 px.", REF["image"]))
        by_img = {}
        for p in products:
            im = (p.get("images") or [None])[0]
            src = re.sub(r"^https?:|\?.*$", "", str(im.get("src") or "")) if isinstance(im, dict) else ""
            if src and not GIFT.search(p.get("title", "")):
                by_img.setdefault(src, []).append(p["title"])
        shared = sorted((t for t in by_img.values() if len({_base(x) for x in t}) >= 3), key=len, reverse=True)
        if shared:
            C.append(_check("D17", A2, "middel", "Hver vare har sit eget billede", "advarsel",
                            f"Det samme billede bruges på {len(shared[0])} forskellige varer, fx '{shared[0][0][:40]}' og '{shared[0][1][:40]}'",
                            "Google vil se den vare, der sælges. Et fælles billede på mange varer ligner et pladsholder-billede, og varerne kan blive afvist eller vist dårligt.",
                            "Upload et rigtigt billede af hver vare.", REF["image"]))
        pre = [p["title"] for p in products if PREORDER.search(p.get("title", "") + " " + " ".join(p.get("tags") or []))]
        if pre:
            C.append(_check("D21", A2, "lav", "Forudbestillingsvarer er markeret rigtigt", "advarsel", f"{len(pre)} varer er markeret som forudbestilling (i titel eller tags), fx '{pre[0][:50]}'",
                            "Google kræver, at forudbestillingsvarer har lagerstatus 'preorder' og en dato for, hvornår de kan leveres. Ellers kan de blive afvist.",
                            "Sæt lagerstatus til forudbestilling og en leveringsdato i Google-kanalen eller feed-appen.", REF["availability"]))
        one = [p["title"] for p in products if len(p.get("title", "").split()) == 1 and not GIFT.search(p.get("title", ""))]
        if len(products) >= 10 and len(one) >= len(products) / 2:
            C.append(_check("D20", A2, "lav", "Produkttitlerne beskriver varen", "advarsel", f"{len(one)} af {len(products)} titler er kun ét ord, fx '{one[0][:40]}'",
                            "Google matcher søgninger med titlen. En titel som 'Kjole' rammer langt færre søgninger end 'Mærke kjole i hør, sort, str. 38'.",
                            "Skriv titler som 'Mærke + produkttype + egenskab (farve, materiale, størrelse)'.", REF["title"]))
        long_t = [p["title"].strip() for p in products if len((p.get("title") or "").strip()) > 150]
        if long_t:
            C.append(_check("D24", A2, "lav", "Produkttitlerne er højst 150 tegn", "advarsel",
                            f"{len(long_t)} titler er over 150 tegn, fx '{long_t[0][:60]}…' ({len(long_t[0])} tegn)",
                            "Google tillader højst 150 tegn i en titel. Resten bliver skåret af, så det vigtigste skal stå først.",
                            "Kort titlen ned til under 150 tegn, med mærke og produkttype først.", REF["title"]))
        long_d = [(p["title"], len(t)) for p in products for t in [re.sub(r"\s+", " ", _text(p.get("body_html") or "")).strip()] if len(t) > 5000]
        if long_d:
            C.append(_check("D25", A2, "lav", "Produktbeskrivelserne er højst 5.000 tegn", "advarsel",
                            f"{len(long_d)} beskrivelser er over 5.000 tegn, fx '{long_d[0][0][:50]}' ({long_d[0][1]} tegn)",
                            "Google tillader højst 5.000 tegn i en beskrivelse. Længere tekst bliver skåret af eller giver en fejl i feedet.",
                            "Kort beskrivelsen ned, og flyt fx vaskeanvisning og fragtinfo ud af produktteksten.", REF["title"]))
        emo = [p["title"] for p in products if EMOJI.search(p.get("title", ""))]
        if emo:
            C.append(_check("D19", A2, "middel", "Produkttitler uden emojis", "advarsel", f"{len(emo)} titler med emojis eller symboler, fx '{emo[0][:60]}'",
                            "Googles regler for titler tillader ikke emojis og pyntesymboler. Titler med dem kan blive afvist.",
                            "Fjern emojis og symboler fra titlerne. Brug dem gerne i beskrivelsen i stedet.", REF["title"]))
        by_desc = {}
        for p in products:
            d = re.sub(r"\s+", " ", _text(p.get("body_html") or "")).strip().lower()
            if len(d) >= 60:
                by_desc.setdefault(d, []).append(p["title"])
        same_desc = sorted((t for t in by_desc.values() if len({_base(x) for x in t}) >= 5), key=len, reverse=True)
        if same_desc:
            C.append(_check("D18", A2, "lav", "Hver vare har sin egen beskrivelse", "advarsel",
                            f"Den samme beskrivelse står på {len(same_desc[0])} forskellige varer, fx '{same_desc[0][0][:40]}' og '{same_desc[0][1][:40]}'",
                            "Når mange varer har præcis samme tekst, har Google svært ved at skelne dem, og varerne matcher færre søgninger.",
                            "Skriv det, der er særligt for hver vare: mål, materiale, farve og brug.", REF["title"]))
        draft = [p["title"] for p in products if DRAFT.search(p.get("title", ""))]
        if draft:
            C.append(_check("D16", A2, "middel", "Ingen kladde- eller testvarer i butikken", "advarsel", f"{len(draft)} varer ligner kladder eller tests, fx '{draft[0][:60]}'",
                            "Varer som 'Copy of …' eller 'Test' er synlige for kunder og kommer med i Google-feedet, hvor de ser ufærdige ud.",
                            "Skjul eller slet varerne, eller giv dem en rigtig titel.", REF["misrep"]))
        low = []
        for p in products:
            vs = [(float(v.get("price") or 0), v.get("title") or "") for v in p.get("variants", [])]
            real = [(pr, t) for pr, t in vs if pr > 0 and not SAMPLE.search(t)]
            hi = max((pr for pr, _ in real), default=0)
            tiny = [(pr, t) for pr, t in real if pr <= 1]  # a price of 1 kr. or less next to a real price is a placeholder, not a size
            if tiny and hi >= 50 and not SAMPLE.search(p.get("title", "")):
                low.append((p["title"], tiny[0][1], tiny[0][0], hi))
        if low:
            t, vt, lo, hi = low[0]
            C.append(_check("D15", A2, "middel", "Ingen varianter med mistænkeligt lav pris", "advarsel",
                            f"{len(low)} varer har en variant til højst 1 kr., mens samme vare ellers koster op til {hi:.0f} kr., fx '{t[:50]}' (varianten '{vt[:30]}')",
                            "En variant til få kroner ligner en fejlpris. Google viser den laveste pris, og kunder, der bestiller den, kan kræve at få varen til den pris.",
                            "Tjek prisen på varianten, og ret den, hvis den er forkert.", REF["price"]))
        demo_p = [p["title"] for p in products if DEMO_PRODUCT.search(p.get("title", "") + " " + _text(p.get("body_html") or ""))]
        if demo_p:
            C.append(_check("D11", A2, "høj", "Ingen demo-varer eller fyldtekst", "fejl", f"{len(demo_p)} varer med demo- eller fyldtekst, fx '{demo_p[0][:60]}'",
                            "Varer med 'lorem ipsum' eller demo-tekst ligner en ufærdig butik og bliver afvist, hvis de kommer med i Google-feedet.",
                            "Slet demo-varerne, eller skriv rigtige titler og beskrivelser.", REF["misrep"]))
        same = Counter(re.sub(r"\s+", " ", p.get("title", "")).strip().lower() for p in products if p.get("title"))
        dups = [(t, c) for t, c in same.most_common() if c > 1]
        if len(dups) >= 3:
            first = next(p["title"] for p in products if re.sub(r"\s+", " ", p.get("title", "")).strip().lower() == dups[0][0])
            C.append(_check("D13", A2, "lav", "Hver vare har sin egen titel", "advarsel", f"{len(dups)} titler bruges af flere varer, fx '{first[:60]}' ({dups[0][1]} varer)",
                            "Når flere varer har præcis samme titel, kan Google og kunderne ikke se forskel på dem i søgeresultaterne.",
                            "Skriv det, der adskiller varerne, i titlen (fx farve, størrelse eller model).", REF["title"]))
        sold = [p["title"] for p in products if p.get("variants") and not any(v.get("available") for v in p["variants"])]
        if len(products) >= 10 and len(sold) >= len(products) / 2:
            C.append(_check("D12", A2, "lav", "De fleste varer kan købes", "advarsel", f"{len(sold)} af {len(products)} varer er udsolgt, fx '{sold[0][:60]}'",
                            "Udsolgte varer vises ikke i Google Shopping-annoncer, og en butik med mest udsolgte varer virker inaktiv.",
                            "Skjul udsolgte varer, der ikke kommer igen, eller fyld lageret op.", REF["availability"]))
        if len(products) < 3:
            C.append(_check("M04", A4, "høj", "Butikken har et reelt sortiment", "fejl", f"Kun {len(products)} varer fundet.",
                            "En næsten tom butik ligner en ufærdig eller useriøs side.", "Tilføj flere varer, eller vent med Google Shopping.", REF["misrep"]))

    # ---------- GTIN + price/availability consistency on sampled product pages ----------
    if pp:
        js_vars = [v for _, _, js in pp if js for v in js.get("variants", [])]
        if js_vars:
            nobar = [v for v in js_vars if not (v.get("barcode") or "").strip()]
            share = len(nobar) / len(js_vars)
            C.append(_check("D03", A2, "middel", "Varer har stregkode (GTIN/EAN)", "advarsel" if share > 0.5 else "ok",
                            f"{share:.0%} af {len(js_vars)} varianter på {len(pp)} stikprøvevarer mangler stregkode.",
                            "Mærkevarer uden GTIN får ofte begrænset synlighed eller afvises. Egne produkter uden GTIN skal markeres korrekt (identifier_exists).",
                            "Udfyld stregkode/GTIN for mærkevarer. Ved egne produkter: brug mærke + varenummer (MPN), eller marker 'ingen GTIN' i feed-appen.", REF["gtin"]))
            noid = [v for v in js_vars if not str(v.get("barcode") or "").strip() and not str(v.get("sku") or "").strip()]
            if len(noid) > len(js_vars) / 2:
                C.append(_check("D14", A2, "lav", "Varer har stregkode eller varenummer", "advarsel",
                                f"{len(noid)} af {len(js_vars)} varianter på {len(pp)} stikprøvevarer har hverken stregkode eller varenummer (SKU).",
                                "Uden stregkode skal Google bruge mærke og varenummer til at genkende varen. Uden nogen af delene bliver varen sværere at matche.",
                                "Udfyld varenummer (SKU) på alle varianter, og stregkode på mærkevarer.", REF["gtin"]))
        bad_gtin = [((v.get("name") or v.get("title") or "").replace("'", "’")[:50], str(v["barcode"]).strip()) for v in js_vars
                    if str(v.get("barcode") or "").strip() and not gtin_ok(v["barcode"])]
        if bad_gtin:
            C.append(_check("D10", A2, "høj", "Stregkoderne er gyldige GTIN", "fejl",
                            f"{len(bad_gtin)} af {len(js_vars)} varianter på {len(pp)} stikprøvevarer har en ugyldig stregkode, fx '{bad_gtin[0][0]}' med stregkoden {bad_gtin[0][1]}",
                            "Google tjekker stregkodens kontrolciffer. En ugyldig GTIN giver afviste varer eller begrænset visning.",
                            "Ret stregkoden til producentens rigtige EAN/GTIN, eller fjern den, hvis varen ikke har en.", REF["gtin"]))
        resv = [((v.get("name") or v.get("title") or "").replace("'", "’")[:50], str(v["barcode"]).strip()) for v in js_vars
                if str(v.get("barcode") or "").strip() and gtin_ok(v["barcode"]) and gtin_reserved(v["barcode"])]
        if resv:
            C.append(_check("D22", A2, "høj", "Stregkoderne er rigtige EAN fra producenten", "fejl",
                            f"{len(resv)} af {len(js_vars)} varianter på {len(pp)} stikprøvevarer har en butiksintern stregkode, fx '{resv[0][0]}' med stregkoden {resv[0][1]}",
                            "Stregkoder, der starter med 2, 02 eller 04, er numre til butikkens eget brug (fx vægtvarer). Google godtager dem ikke som GTIN.",
                            "Brug producentens rigtige EAN. Har varen ingen, så fjern stregkoden og marker 'ingen GTIN' i feed-appen.", REF["gtin"]))
        def ean_like(s):  # a real EAN-13/UPC typed into the SKU field (short or zero-padded numbers are often plain item numbers)
            s = str(s or "").strip()
            return bool(re.fullmatch(r"\d{12,14}", s)) and len(s.lstrip("0")) >= 11 and gtin_ok(s)
        sku_only = [((v.get("name") or v.get("title") or "").replace("'", "’")[:50], str(v["sku"]).strip()) for v in js_vars
                    if ean_like(v.get("sku")) and not str(v.get("barcode") or "").strip()]
        if sku_only:
            C.append(_check("D26", A2, "middel", "Stregkoden står i stregkode-feltet", "advarsel",
                            f"{len(sku_only)} af {len(js_vars)} varianter på {len(pp)} stikprøvevarer har en EAN i varenummer-feltet (SKU), men stregkode-feltet er tomt, fx '{sku_only[0][0]}' med {sku_only[0][1]}",
                            "Shopify sender kun stregkode-feltet til Google som GTIN. Står EAN'en i varenummer-feltet, får Google den ikke, og varen bliver sværere at matche.",
                            "Kopiér EAN'en over i feltet 'Stregkode (ISBN, UPC, GTIN osv.)' på hver variant. Det kan gøres for alle varer på én gang med en CSV-eksport og -import.", REF["gtin"]))
        by_bar = {}
        for v in js_vars:
            b = re.sub(r"\s", "", str(v.get("barcode") or ""))
            if b and gtin_ok(b) and not gtin_reserved(b):
                by_bar.setdefault(b.lstrip("0"), []).append((v.get("name") or v.get("title") or "").replace("'", "’")[:50])
        dup_bar = sorted((t for t in by_bar.values() if len(t) >= 2), key=len, reverse=True)
        if dup_bar:
            C.append(_check("D23", A2, "middel", "Hver variant har sin egen stregkode", "advarsel",
                            f"Den samme stregkode står på {len(dup_bar[0])} varianter, fx '{dup_bar[0][0]}' og '{dup_bar[0][1]}'",
                            "En stregkode hører til præcis én vare i én størrelse og farve. Står den på flere varianter, kan Google ikke se forskel og viser den forkerte variant eller afviser dem.",
                            "Giv hver variant producentens egen EAN. Har varianterne ingen, så fjern stregkoden og marker 'ingen GTIN'.", REF["gtin"]))
        no_ld, mism, avail_bad, comma, cur_bad, ld_gap, gtin_lost, dup_ld, no_brand = [], [], [], [], [], [], [], [], []
        no_avail, expired, name_bad = [], [], []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for prod, b, js in pp:
            items = [x for x in _ldjson(b) if str(x.get("@type", "")).lower() in ("product", "productgroup")]
            if not items:
                if not re.search(r'itemtype=["\']https?://schema\.org/Product["\']', b, re.I):  # microdata also counts
                    no_ld.append(prod["title"])
                continue
            offers = _offers(items)
            shop_cur = re.search(r'Shopify\.currency\s*=\s*\{"active":"([A-Z]{3})"', b)
            ld_cur = {str(o.get("priceCurrency") or "").upper() for o in offers if o.get("priceCurrency")}
            if shop_cur and ld_cur and shop_cur.group(1) not in ld_cur:
                cur_bad.append(f"{prod['title'][:40]}: {', '.join(sorted(ld_cur))} i stedet for {shop_cur.group(1)}")
            raw_prices = [o.get("price") for o in offers if o.get("price") not in (None, "")]
            name = re.sub(r"\s+", " ", prod["title"]).strip().lower()
            words = set(re.findall(r"[a-zæøå0-9]+", name))
            def overlap(n):
                w = set(re.findall(r"[a-zæøå0-9]+", str(n or "").lower()))
                return len(words & w) / max(1, min(len(words), len(w)))
            names = [it.get("name") for it in items if it.get("name")]
            if names and words and max(overlap(n) for n in names) < 0.3:
                name_bad.append(f"'{prod['title'][:40]}' hedder '{str(names[0])[:40]}' i produktdataene")
            same_item = [it for it in items if re.sub(r"\s+", " ", str(it.get("name") or "")).strip().lower() == name]
            if len(same_item) >= 2:
                dup_ld.append(f"{prod['title'][:40]}: {len(same_item)} sæt")
            if not any(it.get("brand") for it in items):
                no_brand.append(prod["title"][:40])
            good = [v for v in (js or {}).get("variants", []) if str(v.get("barcode") or "").strip() and gtin_ok(v["barcode"])]
            if good and not re.search(r'"gtin(?:8|12|13|14)?"', json.dumps(items)):
                gtin_lost.append(f"'{prod['title'][:40]}' har stregkoden {str(good[0]['barcode']).strip()} i butikken")
            if offers and any(not o.get("availability") for o in offers):
                no_avail.append(prod["title"][:40])
            dates = [re.search(r"\d{4}-\d{2}-\d{2}", str(o.get("priceValidUntil") or "")) for o in offers]
            old = sorted(m.group(0) for m in dates if m and m.group(0) < today)
            if old:
                expired.append(f"'{prod['title'][:40]}' har en pris, der udløb {old[0]}")
            missing = [w for w, ok in (("billede", any(it.get("image") or any(isinstance(hv, dict) and hv.get("image") for hv in it.get("hasVariant") or []) for it in items)), ("pris", bool(raw_prices))) if not ok]
            if missing:
                ld_gap.append(f"{prod['title'][:40]}: mangler {' og '.join(missing)}")
            if any(isinstance(p, str) and "," in p for p in raw_prices):
                comma.append(f"{prod['title'][:40]}: '{next(p for p in raw_prices if isinstance(p, str) and ',' in p)}'")
            ld_prices = {round(v, 2) for v in (_num(p) for p in raw_prices) if v is not None}
            if js and ld_prices:
                js_prices = {round(int(v.get("price") or 0) / 100, 2) for v in js.get("variants", [])}
                if js_prices and not (ld_prices & js_prices):
                    mism.append(f"{prod['title'][:40]}: strukturerede data {sorted(ld_prices)[:2]} vs. butikkens pris {sorted(js_prices)[:2]}")
                ld_av = {str(o.get("availability", "")).rsplit("/", 1)[-1].lower() for o in offers}
                js_av = any(v.get("available") for v in js.get("variants", []))
                if ld_av and (("instock" in ld_av) != js_av):
                    avail_bad.append(prod["title"][:40])
        C.append(_check("S01", A3, "middel", "Produktsider har strukturerede produktdata", "advarsel" if no_ld else "ok",
                        f"Mangler på {len(no_ld)} af {len(pp)} tjekkede sider" if no_ld else f"{len(pp)} sider tjekket.",
                        "Google sammenligner feedet med produktsiden. Strukturerede data gør det lettere at få varer godkendt automatisk.",
                        "Brug et tema eller en app, der udsender Product-data (JSON-LD) med pris og lagerstatus.", REF["price"]))
        C.append(_check("S02", A3, "høj", "Pris i strukturerede data passer med den viste pris", "fejl" if mism else "ok",
                        "; ".join(mism[:2]) if mism else "Priserne stemmer på de tjekkede sider.",
                        "Prisforskelle mellem feed/strukturerede data og den viste pris er en af de hyppigste årsager til afviste varer.",
                        "Sørg for, at tema/app udsender samme pris og valuta som den viste pris, også ved tilbud og i alle markeder.", REF["price"]))
        if comma:
            C.append(_check("S05", A3, "middel", "Pris i strukturerede data bruger punktum som decimaltegn", "advarsel",
                            "; ".join(comma[:2]),
                            "Strukturerede data skal skrive prisen med punktum (fx 349.00). Med komma ('349,00') kan Google læse prisen forkert eller ikke kunne bruge den.",
                            "Ret temaets JSON-LD, så prisen udskrives uden tusindtalsskilletegn og med punktum som decimaltegn.", REF["price"]))
        if ld_gap:
            C.append(_check("S07", A3, "middel", "Strukturerede produktdata har billede og pris", "fejl", "; ".join(ld_gap[:2]),
                            "Google bruger produktdataene i koden til at vise og tjekke varen. Uden billede eller pris kan varen ikke vises med pris i Google.",
                            "Ret temaets JSON-LD, så hver vare har image, price og priceCurrency.", REF["price"]))
        if expired:
            C.append(_check("S12", A3, "middel", "Prisen i produktdataene er ikke udløbet", "advarsel", "; ".join(expired[:2]) + ".",
                            "Produktdataene på siden siger, at prisen kun gælder til en dato, der er overstået. Så kan Google se prisen som forældet.",
                            "Fjern priceValidUntil fra temaets JSON-LD, eller sæt en dato i fremtiden.", REF["price"]))
        if no_avail:
            C.append(_check("S11", A3, "lav", "Produktdataene har lagerstatus", "advarsel", f"Lagerstatus mangler i produktdataene for fx '{no_avail[0]}'.",
                            "Google bruger lagerstatus til at vise, om varen kan købes. Mangler den, skal Google gætte.",
                            "Sørg for at temaets JSON-LD har availability på alle tilbud.", REF["availability"]))
        site = _site(final)
        other = []
        for prod, b, _ in pp:
            m = re.search(r"""<link[^>]+rel=["']canonical["'][^>]*>""", b, re.I)
            href = re.search(r"""href=["']([^"']+)""", m.group(0)) if m else None
            host = urllib.parse.urlsplit(href.group(1)).hostname if href else None
            if host and _site("https://" + host) != site:
                other.append(f"'{prod['title'][:40]}' peger på {host}")
        if other:
            C.append(_check("S13", A3, "middel", "Produktsiderne peger på butikkens eget domæne", "fejl", "; ".join(other[:2]) + f" som den rigtige adresse (canonical), men butikken ligger på {urllib.parse.urlsplit(final).hostname}.",
                            "Google bruger canonical-adressen som varens rigtige side. Peger den på et andet domæne, passer siden ikke med linket i feedet.",
                            "Sæt butikkens eget domæne som primært domæne i Shopify, og ret temaet, hvis det skriver canonical selv.", REF["misrep"]))
        if gtin_lost:
            C.append(_check("S09", A3, "middel", "Stregkoden står i produktdataene", "advarsel", "; ".join(gtin_lost[:2]) + ", men den står ikke i produktdataene på siden.",
                            "Google sammenligner feedet med produktsiden. Når stregkoden kun findes i butikken og ikke i produktdataene, kan Google ikke bekræfte den.",
                            "Ret temaets JSON-LD, så hver variant har gtin (stregkoden) med.", REF["gtin"]))
        if name_bad:
            C.append(_check("S15", A3, "middel", "Navnet i produktdataene passer med titlen", "advarsel", "; ".join(name_bad[:2]) + ".",
                            "Google sammenligner varens navn i produktdataene med titlen i feedet. Passer de ikke, kan Google ikke se, at det er samme vare.",
                            "Ret temaets JSON-LD, så name er varens titel.", REF["title"]))
        if dup_ld:
            C.append(_check("S10", A3, "middel", "Én vare har ét sæt produktdata", "advarsel", "; ".join(dup_ld[:2]) + " produktdata for samme vare.",
                            "Når både temaet og en app udskriver produktdata, ser Google to versioner af samme vare. Er de forskellige, kan Google vælge den forkerte pris eller lagerstatus.",
                            "Slå produktdata fra i enten temaet eller SEO-appen, så der kun er ét sæt.", REF["price"]))
        if no_brand and len(no_brand) == len(pp):
            C.append(_check("S08", A3, "lav", "Produktdataene har mærke", "advarsel", f"Mærke (brand) mangler i produktdataene på alle {len(pp)} tjekkede sider.",
                            "Google bruger mærket til at genkende varen og vise den på de rigtige søgninger.",
                            "Udfyld 'Leverandør' på varerne, og sørg for at temaet udskriver brand i JSON-LD.", REF["gtin"]))
        if cur_bad:
            C.append(_check("S06", A3, "høj", "Valutaen i strukturerede data passer med butikken", "fejl", "; ".join(cur_bad[:2]),
                            "Google afviser varer, når valutaen i produktdata ikke passer med den valuta, kunden ser på siden.",
                            "Ret temaets JSON-LD, så priceCurrency er butikkens valuta (fx DKK) i alle markeder.", REF["price"]))
        C.append(_check("S03", A3, "middel", "Lagerstatus i strukturerede data passer med butikken", "advarsel" if avail_bad else "ok",
                        ", ".join(avail_bad[:3]) if avail_bad else "Lagerstatus stemmer på de tjekkede sider.",
                        "Uoverensstemmende lagerstatus giver afvisninger og dårlige kundeoplevelser.",
                        "Synkroniser lager, og lad udsolgte varer markeres som udsolgt i feedet.", REF["availability"]))

    # ---------- unit price for goods sold by weight or volume (prismærkningsreglerne) ----------
    by_qty = [p for p in products if QTY.search(p.get("title", "")) and not CONTAINER.search(p.get("title", "") + " " + (p.get("product_type") or ""))]
    if len(by_qty) >= 3:
        seen = {prod.get("handle"): (b, js) for prod, b, js in pp}
        probe = next((p for p in by_qty if p.get("handle") in seen), None)
        body, pjs = seen.get(probe["handle"]) if probe else (None, None)
        if probe is None:
            probe = by_qty[len(by_qty) // 2]
            sb, fin, _, body = f.get(f"/products/{probe['handle']}")
            body = body if sb == 200 else None
            if body:
                sj, _, _, jb = f.get(urllib.parse.urlsplit(fin).path.rstrip("/") + ".js")
                try:
                    pjs = json.loads(jb) if sj == 200 else None
                except ValueError:
                    pjs = None
        if body and pjs is not None:
            set_up = any(v.get("unit_price_measurement") or v.get("unit_price") for v in pjs.get("variants", []))
            if not set_up and not UNIT_SHOWN.search(_text(body)):
                C.append(_check("S16", A3, "middel", "Varer solgt efter vægt eller rumfang viser pris pr. kg/liter", "advarsel",
                                f"{len(by_qty)} varer sælges efter vægt eller rumfang, men fx '{probe['title'][:50]}' viser ingen pris pr. kg eller liter.",
                                "Efter prismærkningsreglerne skal varer, der sælges efter vægt eller rumfang, som udgangspunkt vise prisen pr. kg eller liter. Google bruger også enhedsprisen i annoncen.",
                                "Udfyld 'Enhedspris' (samlet mængde og basisenhed) på varianterne i Shopify, så temaet viser fx '35,00 kr / 100 g'.", REF["price"]))

    # ---------- used goods must say so (Google's condition attribute) ----------
    def _used(p):
        if USED.search(p.get("title", "") + " | " + (p.get("product_type") or "")):
            return True
        return any(USED.search(t) or t.strip().lower() == "used" for t in (p.get("tags") or []))
    used = [p for p in products if _used(p)]
    if used:
        seen = {prod.get("handle"): b for prod, b, _ in pp}
        probe = next((p for p in used if p.get("handle") in seen), None)
        body = seen.get(probe["handle"]) if probe else None
        if probe is None:
            probe = used[0]
            sb, _, _, body = f.get(f"/products/{probe['handle']}")
            body = body if sb == 200 else None
        if body:
            items = [x for x in _ldjson(body) if str(x.get("@type", "")).lower() in ("product", "productgroup")]
            conds = set(re.findall(r'"itemCondition"\s*:\s*"(?:https?://schema\.org/)?(\w+)"', json.dumps(items)))
            conds |= set(re.findall(r"""itemprop=["']itemCondition["'][^>]*(?:href|content)=["'](?:https?://schema\.org/)?(\w+)""", body, re.I))
            if not conds & {"UsedCondition", "RefurbishedCondition", "DamagedCondition"}:
                C.append(_check("D27", A2, "høj", "Brugte varer er markeret som brugte", "advarsel",
                                f"{len(used)} varer er markeret som brugte eller renoverede i titel, type eller tags (fx '{probe['title'][:50]}'), men produktdataene på siden siger "
                                + (f"'{sorted(conds)[0]}'" if conds else "ikke, at varen er brugt") + ".",
                                "Google kræver, at brugte og renoverede varer har tilstanden 'brugt' eller 'renoveret'. Shopifys Google-kanal sender som udgangspunkt 'ny', og en brugt vare solgt som ny ses som vildledning.",
                                "Sæt tilstanden til 'Brugt' (eller 'Renoveret') på de brugte varer i Google & YouTube-kanalen, og få temaet til at skrive itemCondition i produktdataene.", REF["misrep"]))

    # ---------- policy pages we can read (normal /pages/ pages; Shopify's /policies/ is blocked by robots) ----------
    dead, empty, law_txt = [], [], []
    for k in ("returns", "shipping", "terms"):
        if k not in pol_pages:
            continue
        path, label = pol_pages[k]
        sp, _, _, bp = f.get(path)
        if sp in ("robots", "cap") or sp is None:
            continue
        if sp == 404:
            dead.append(f"'{label[:40]}' ({path}) giver 'side ikke fundet'")
            continue
        if sp != 200:
            continue
        body = _main_text(bp)
        if k in ("returns", "terms"):
            law_txt.append((path, body))
        if len(body) < 150:  # could be filled in by an app's script, so only a warning
            empty.append(f"'{label[:40]}' ({path}) viser næsten ingen tekst")
            continue
        if k == "returns" and not LONG_RETURN.search(body):
            short = []
            for m in DAYS.finditer(body):
                near = body[max(0, m.start() - 80): m.end() + 40]
                if RETURN_CTX.search(near) and not MONEY_CTX.search(body[max(0, m.start() - 50): m.end() + 15]):
                    short.append((int(m.group(1)), body[max(0, m.start() - 60): m.end() + 10].strip()))
            if short:
                n, ctx = min(short)
                C.append(_check("P06", A1, "høj", "Returpolitikken giver mindst 14 dages fortrydelsesret", "fejl",
                                f"Returpolitikken ({path}) siger {n} dage: '…{ctx}…'",
                                "Forbrugere har ret til mindst 14 dages fortrydelsesret ved køb på nettet. Google tjekker også, at returpolitikken er tydelig og korrekt.",
                                "Skriv 14 dages fortrydelsesret (eller mere) i returpolitikken, og forklar hvordan kunden returnerer.", REF["misrep"]))
        if k == "shipping" and not SHIP_PRICE.search(body):
            C.append(_check("P07", A1, "middel", "Fragtsiden viser fragtpriser", "advarsel", f"Ingen fragtpriser fundet på {path}.",
                            "Kunder og Google skal let kunne se, hvad fragten koster. Fragtprisen i Merchant Center skal passe med det, kunden betaler.",
                            "Skriv fragtpriser og leveringstid på fragtsiden, fx 'GLS pakkeshop 39 kr., 1-3 hverdage'.", REF["misrep"]))
    if dead or empty:
        C.append(_check("P05", A1, "høj", "Links til politikker virker", "fejl" if dead else "advarsel", "; ".join((dead + empty)[:2]),
                        "Når et link til en politik er dødt eller tomt, ser Google det som en manglende politik, og kunderne kan ikke finde oplysningerne.",
                        "Ret linket, eller udfyld siden med den rigtige politik.", REF["misrep"]))

    # ---------- return terms that break forbrugeraftaleloven ----------
    law_txt = [(p, t) for p, t in law_txt if t]
    if not any(p == "/policies/refund-policy" for p, _ in law_txt):  # Shopify's own refund policy often says more
        sr, _, _, br = f.get("/policies/refund-policy")
        if sr == 200:
            law_txt.append(("/policies/refund-policy", _main_text(br)))
    hygiene_shop = products and sum(1 for p in products if HYGIENE_SHOP.search(p.get("title", "") + " " + (p.get("product_type") or ""))) > len(products) * 0.3
    unopened, from_order = None, None
    for p, t in law_txt:
        sents = re.split(r"(?<=[.!?])\s+", t)
        for i, sent in enumerate(sents):
            near = " ".join(sents[max(0, i - 1): i + 1])  # abbreviations ('mf.') and 'returret i 365 dage. Returretten er ...' span two pieces
            if unopened is None and not hygiene_shop and WITHDRAW.search(sent) and UNOPENED.search(sent) \
                    and not LAW_EXEMPT.search(near) and not LONG_RIGHT.search(near):
                unopened = (p, sent.strip()[:170])
            m = FROM_ORDER.search(sent)
            if from_order is None and m and not re.search(r"modtag", sent, re.I):
                from_order = (p, sent.strip()[:170])
    if unopened:
        C.append(_check("P08", A1, "middel", "Fortrydelsesretten kræver ikke ubrudt emballage", "advarsel",
                        f"Betingelserne ({unopened[0]}) siger: '{unopened[1]}'",
                        "Efter forbrugeraftaleloven må kunden åbne varen og undersøge den, ligesom i en fysisk butik. Fortrydelsesretten må derfor ikke kræve ubrudt emballage; butikken kan i stedet trække et beløb fra, hvis varen er blevet mindre værd. Undtaget er forseglede varer, der af hygiejne- eller sundhedshensyn ikke kan returneres, når forseglingen er brudt.",
                        "Fjern kravet om ubrudt eller uåbnet emballage fra fortrydelsesretten, og skriv i stedet, at kunden hæfter for en eventuel værdiforringelse.", REF["misrep"]))
    if from_order:
        C.append(_check("P09", A1, "middel", "Fortrydelsesfristen regnes fra modtagelsen", "advarsel",
                        f"Betingelserne ({from_order[0]}) siger: '{from_order[1]}'",
                        "Ved køb af varer løber de 14 dages fortrydelsesret fra den dag, kunden modtager varen, ikke fra købet eller afsendelsen.",
                        "Skriv, at fristen på 14 dage regnes fra den dag, kunden har modtaget varen.", REF["misrep"]))

    # ---------- trust & red flags ----------
    scar = SCARCITY.search(home_txt)
    for _, b, _ in pp:
        scar = scar or SCARCITY.search(_text(b))
    timers = TIMER_APPS.search(home) or next((TIMER_APPS.search(b) for _, b, _ in pp if TIMER_APPS.search(b)), None)
    hit = (scar.group(0) if scar else "") or (timers.group(0) if timers else "")
    C.append(_check("M02", A4, "middel", "Ingen kunstig knaphed eller nedtællinger", "advarsel" if hit else "ok",
                    f"Fundet: '{hit}'" if hit else "Intet fundet.",
                    "Falske nedtællinger og 'kun 2 tilbage'-tekster ses af Google som vildledende og hænger ofte sammen med suspendering.",
                    "Fjern nedtællings- og knaphedsapps, medmindre tallene er ægte.", REF["misrep"]))
    demo = DEMO.search(home_txt)
    if demo:
        C.append(_check("M05", A4, "høj", "Ingen demo-tekst fra temaet på forsiden", "fejl", f"fx '{demo.group(0)}'",
                        "Demo-tekst fra temaet får butikken til at se ufærdig ud. Google kan afvise butikker, der virker ufærdige.",
                        "Erstat temaets eksempeltekster med jeres egne tekster, eller fjern sektionerne.", REF["misrep"]))
    years = [int(y) for y in COPYRIGHT.findall(home_txt)]
    this_year = datetime.now(timezone.utc).year
    if years and max(years) <= this_year - 2:
        C.append(_check("M06", A4, "lav", "Årstallet i footeren er opdateret", "advarsel", f"Footeren siger © {max(years)}.",
                        "Et gammelt årstal får siden til at se forladt ud for både kunder og Google.",
                        "Brug temaets automatiske årstal, eller ret det til i år.", None))
    exv = EX_VAT.search(home_txt) or next((m for m in (EX_VAT.search(_text(b)) for _, b, _ in pp) if m), None)
    if exv:
        C.append(_check("M15", A4, "middel", "Priserne vises inkl. moms", "advarsel", f"Siden skriver '{exv.group(0)}'.",
                        "Sælger I til private, skal prisen vises inkl. moms. Google tjekker også, at prisen på siden er den, kunden betaler.",
                        "Vis priser inkl. moms, hvis I sælger til private. Sælger I kun til virksomheder, så skriv det tydeligt.", REF["price"]))
    tm = re.search(r"<title[^>]*>(.*?)</title>", home, re.S | re.I)
    title = html.unescape(re.sub(r"\s+", " ", tm.group(1))).strip() if tm else ""
    desc = any(re.search(r"""name=["']description["']""", t, re.I) and re.search(r"""content=["'][^"']{20,}""", t, re.I)
               for t in META_TAG.findall(home[:200_000]))
    generic = bool(GENERIC_TITLE.fullmatch(title))
    if generic or not desc:
        C.append(_check("M09", A4, "lav", "Forsiden har en titel og beskrivelse til Google", "advarsel",
                        f"Forsidens titel er '{title or 'tom'}'." if generic else "Forsiden har ingen beskrivelse (meta description).",
                        "Titel og beskrivelse er det, kunderne ser om butikken i Google. Mangler de, finder Google selv på en tekst.",
                        "Skriv en titel og beskrivelse under Onlinebutik → Præferencer.", None))
    lang = HTML_LANG.search(home)
    words = re.findall(r"[a-zæøå]+", home_txt.lower())
    da, en = sum(w in DA_WORDS for w in words), sum(w in EN_WORDS for w in words)
    if lang and not lang.group(1).lower().startswith(("da", "no", "nb", "sv")) and da >= 20 and da > 2 * en:
        C.append(_check("M11", A4, "middel", "Siden er sat til det rigtige sprog", "advarsel",
                        f"Siden er sat til sproget '{lang.group(1)}', men teksten er dansk ({da} almindelige danske ord mod {en} engelske).",
                        "Browsere og Google bruger sproget i koden. Står der et andet sprog end teksten, kan siden blive tilbudt oversat, og det ser uprofessionelt ud.",
                        "Sæt butikkens standardsprog til dansk under Indstillinger → Sprog.", None))
    under = UNDER.search(home_txt)
    if under:
        C.append(_check("M12", A4, "middel", "Forsiden siger ikke, at butikken er under opbygning", "advarsel", f"Forsiden siger '{under.group(0)}'.",
                        "Google afviser butikker, der ser ufærdige ud, og kunder handler sjældent i en butik, der siger, den ikke er klar.",
                        "Fjern teksten, når butikken er klar, eller lås butikken med adgangskode, indtil den er det.", REF["misrep"]))
    rb = getattr(f, "robots_txt", "")
    if rb:
        blocked = []
        for token in ("googlebot", "storebot-google"):
            g = Robots(rb, token)
            paths = ["/"] + [f"/products/{p['handle']}" for p, _, _ in pp[:1]]
            blocked += [f"{token}: {x}" for x in paths if not g.allowed(x)]
        if blocked:
            C.append(_check("M13", A4, "kritisk", "robots.txt giver Google lov til at læse butikken", "fejl", f"robots.txt forbyder fx {blocked[0]}.",
                            "Google må ikke læse sider, som robots.txt forbyder. Så kan Google hverken finde forsiden eller tjekke produktsiderne.",
                            "Ret robots.txt (i Shopify: temaets robots.txt.liquid), så Googlebot og Storebot-Google må læse butikken.", REF["misrep"]))
    if not re.search(r"""<meta[^>]+name=["']?viewport""", home[:200_000], re.I):
        C.append(_check("M14", A4, "middel", "Siden er sat op til mobil", "advarsel", "Forsiden har ingen viewport-indstilling til mobil.",
                        "Uden viewport vises siden som en lille computerside på mobilen. Google Ads vurderer også, hvor godt siden virker på mobil.",
                        "Tilføj <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> i temaets theme.liquid, eller skift til et moderne tema.", None))
    hi = HTTP_IMG.search(home)
    if hi:
        C.append(_check("M10", A4, "lav", "Alle billeder hentes over sikker forbindelse", "advarsel", f"fx {hi.group(0)[-80:]}",
                        "Billeder over http på en https-side giver advarsler i browseren og kan blive blokeret.",
                        "Upload billedet til Shopify (Indhold → Filer) og brug det nye link.", None))
    ni = noindex(home)
    ni_prod = next((p["title"] for p, b, _ in pp if noindex(b)), None)
    if ni or ni_prod:  # a single hidden product can be on purpose, so only the homepage is an error
        C.append(_check("M07", A4, "høj" if ni else "middel", "Siderne må vises i Google-søgning", "fejl" if ni else "advarsel",
                        f"Forsiden har et 'noindex'-tag: {ni}" if ni else f"Produktsiden for '{ni_prod[:50]}' har et 'noindex'-tag.",
                        "Et 'noindex'-tag beder Google om ikke at vise siden i søgeresultaterne, så kunder ikke kan finde den via Google.",
                        "Fjern 'noindex' fra temaet eller den app, der sætter det (tjek SEO-apps og theme.liquid).", None))
    if final.startswith("http://"):
        C.append(_check("M08", A4, "høj", "Butikken bruger sikker forbindelse (https)", "fejl", final,
                        "Google kræver sikker forbindelse (https) på butik og kasse. Uden https vises 'Ikke sikker' i browseren.",
                        "Slå SSL til for domænet (Onlinebutik → Domæner), så alle sider sender videre til https.", REF["misrep"]))
    myshop = ".myshopify.com" in final
    C.append(_check("M03", A4, "middel", "Butikken bruger eget domæne", "fejl" if myshop else "ok", final,
                    "Et myshopify.com-domæne virker mindre troværdigt for både Google og kunder.",
                    "Tilknyt et eget domæne (fx dinbutik.dk) som primært domæne.", REF["misrep"]))

    # ---------- score ----------
    pen, counts = 0, {"kritisk": 0, "høj": 0, "middel": 0, "lav": 0}
    for c in C:
        if c["status"] == "fejl":
            pen += PENALTY[c["severity"]]
            counts[c["severity"]] += 1
        elif c["status"] == "advarsel":
            pen += PENALTY[c["severity"]] / 2
    res["score"] = max(0, round(100 - pen))
    res["counts"] = counts
    res["n_fail"] = sum(1 for c in C if c["status"] == "fejl")
    res["n_warn"] = sum(1 for c in C if c["status"] == "advarsel")
    res["fetch_log"] = f.log
    return res
