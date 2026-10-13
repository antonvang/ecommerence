// Instant version of the GMC-Doktor checker (gmcdoktor/checks.py) for the "Tjek din webshop" field on webshopdoktoren.dk.
// Same ids, texts and design rule: a 'fejl' is only something we actually saw on the public pages. Lighter than the full
// check: homepage, up to 2 contact/about pages, /products.json?limit=100 and 2 product pages (+ .js), robots.txt respected.
export const VERSION = "w0.3.0";
const UA = "Mozilla/5.0 (compatible; GMC-Doktor/0.1; offentligt Merchant Center-tjek af butikssider; webshopdoktoren.dk)";
const PENALTY = {kritisk: 15, "høj": 8, middel: 4, lav: 2};
const SEV = {kritisk: 0, "høj": 1, middel: 2, lav: 3};
const MAX_REQ = 10, MAX_BODY = 1_500_000;

// problem-phrased headings (same as tools/dashboard_seed.py PROBLEM)
export const PROBLEM = {
  M01: "Butikken er låst med adgangskode",
  C01: "CVR-nummeret står ikke på forsiden eller kontaktsiden",
  C02: "Der står ingen fuld adresse på forsiden eller kontaktsiden",
  C03: "Der står intet telefonnummer på forsiden eller kontaktsiden",
  C04: "Der står ingen e-mailadresse på forsiden eller kontaktsiden",
  C05: "Intet link til en kontakt- eller om os-side på forsiden",
  C06: "CVR-nummeret på siden er ugyldigt",
  P01: "Intet direkte link til returpolitik / fortrydelsesret",
  P02: "Intet direkte link til fragt- og leveringsinfo",
  P03: "Intet direkte link til handelsbetingelser",
  P04: "Intet direkte link til privatlivspolitik",
  D02: "Varer med pris 0 kr.",
  D03: "Varer uden stregkode (GTIN/EAN)",
  D04: "Produkttitler med salgsord eller VERSALER",
  D05: "Varer uden billede",
  D06: "Produkttype mangler på de fleste varer",
  D07: "Mange førpriser med over 50 % rabat",
  D08: "Varer uden produktbeskrivelse",
  D09: "Produktbilleder i for lav opløsning",
  D10: "Ugyldige stregkoder (GTIN/EAN)",
  D11: "Demo-varer eller fyldtekst i butikken",
  D12: "De fleste varer er udsolgt",
  M04: "Meget få varer i butikken",
  S01: "Produktsiderne mangler strukturerede produktdata",
  S02: "Prisen i de strukturerede data passer ikke med den viste pris",
  S03: "Lagerstatus i de strukturerede data passer ikke med butikken",
  S05: "Prisen i de strukturerede data står med komma",
  S06: "Valutaen i de strukturerede data passer ikke med butikken",
  S07: "De strukturerede produktdata mangler billede eller pris",
  M02: "Tekst om knaphed eller nedtælling på siden",
  M03: "Butikken bruger et myshopify.com-domæne",
  M05: "Demo-tekst fra temaet står stadig på forsiden",
  M06: "Gammelt årstal i footeren",
  M07: "Forsiden beder Google om ikke at vise den (noindex)",
  M08: "Butikken bruger ikke sikker forbindelse (https)",
  M09: "Forsiden mangler titel eller beskrivelse til Google",
  M10: "Billeder hentes over usikker forbindelse (http)",
};
const CONCRETE = new Set(["S05", "D07", "M02", "D04", "S03", "S01", "D08", "D09", "P05"]);

const NB = "(?<![\\p{L}\\p{N}_])"; // a \b that also works before æ, ø and å
const SALES_WORDS = /(gratis fragt|fri fragt|\btilbud\b|\budsalg\b|spar \d+|\brabat\b|nr\.? ?1\b|!!|køb nu|free shipping|\bsale\b|bestseller)/i;
const SCARCITY = /([1-9]\d* (personer|people) (kigger|ser|are viewing)|sælges hurtigt|selling fast|tilbuddet udløber|offer ends in|hurry,? only)/i;
const TIMER_APPS = /(hurrify|essential-countdown|countdown-timer-bar|sales-countdown|fomo-app|stock-countdown|urgency-app)/i;
const EMAIL = /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g;
const PHONE = /(?:\+45[\s\-]?)?\b(?:\d{2}[\s\-]?){3}\d{2}\b/g;
const PHONE_CTX = /(tlf|telefon|ring |phone|mobil|tel\.|tel:)/i;
const CVR = /(?:CVR|CVR[\-\s]?nr\.?|CVR[\-\s]?nummer|VAT(?:[\-\s]?(?:no|nr|number))?\.?|Org\.?\s?nr\.?)\s*[:.\-]?\s*(?:DK[\s\-]?)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})\b/i;
const STREET = new RegExp(NB + "[A-ZÆØÅ][a-zæøåA-ZÆØÅ.\\-]*(?:vej|gade|allé|alle|stræde|torv|plads|vænge|parken|bakke|boulevard|have|toften|marken)(?:en|et|e)?\\s?\\d+[A-Za-z]?", "giu");
const POSTCODE_CITY = new RegExp(NB + "(?:DK[\\-\\s]?)?([1-9]\\d{3})\\s+([A-ZÆØÅ][a-zæøå]+(?:[\\s\\-][A-ZÆØÅ]?[a-zæøå]+)?)", "u");
const POLICY_KEYS = {
  returns: [/\/policies\/refund-policy/, "(retur|fortryd|refund|return|ombyt)"],
  shipping: [/\/policies\/shipping-policy/, "(fragt|levering|forsendelse|shipping|delivery)"],
  terms: [/\/policies\/terms-of-service/, "(handelsbetingelser|betingelser|vilk[aå]r|terms)"],
  privacy: [/\/policies\/privacy-policy/, "(privatliv|persondata|privacy)"],
};
const HELP_LINK = /(faq|hjælp|help|kundeservice|customer service|support|spørgsmål)/i;
const FREE_MAIL = ["gmail.", "hotmail.", "outlook.", "yahoo.", "live.", "icloud."];
const JUNK_MAIL = ["example.", "sentry", "wixpress", "domain.", "email.com", "@2x", ".png", ".jpg", ".webp", "shopify"];
const DEMO = /(talk about your brand|share information about your brand with your customers|pair text with an image to focus on|use this text to share information about your brand|add a tagline|lorem ipsum|example product title|your content goes here|fortæl om dit brand|del oplysninger om dit brand med dine kunder|kombiner tekst med et billede|eksempel på produkttitel)/i;
const DEMO_PRODUCT = /(lorem ipsum|this is a demo|dette er en demo|example product|eksempel på produkt)/i;
const COPYRIGHT = /(?:©|copyright)\s*(?:20\d{2}\s*[-–]\s*)?(20\d{2})/gi;
const GENERIC_TITLE = /^\s*(home|forside|hjem|my store|min butik|welcome|velkommen|shop|webshop)?\s*$/i;
const HTTP_IMG = /<img\b[^>]*\ssrc=["']http:\/\/[^"']+/i;

const ENT = {amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", copy: "©", aelig: "æ", oslash: "ø", aring: "å", AElig: "Æ",
  Oslash: "Ø", Aring: "Å", ndash: "–", mdash: "—", hellip: "…", rsquo: "’", lsquo: "‘", ldquo: "“", rdquo: "”", laquo: "«", raquo: "»",
  eacute: "é", uuml: "ü", ouml: "ö", auml: "ä", Uuml: "Ü", Ouml: "Ö", Auml: "Ä", reg: "®", trade: "™", euro: "€"};
const unescape = s => s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => e[0] === "#"
  ? String.fromCodePoint(e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : (ENT[e] ?? m));
const text = h => unescape((h || "").replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<noscript[\s\S]*?<\/noscript>/gi, " ")
  .replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const links = h => [...(h || "").matchAll(/<a\b[^>]*href="([^"#]+)"[^>]*>([\s\S]*?)<\/a>/gi)].map(m => [unescape(m[1]), text(m[2])]);
const pathOf = href => href.replace(/^https?:\/\/[^/]+/i, "");

function ldjson(h) {
  const out = [];
  for (const m of (h || "").matchAll(/<script[^>]+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi)) {
    let d;
    try { d = JSON.parse(m[1].trim()); } catch { continue; }
    const stack = Array.isArray(d) ? [...d] : [d];
    while (stack.length) {
      const x = stack.pop();
      if (Array.isArray(x)) stack.push(...x);
      else if (x && typeof x === "object") {
        if (x["@graph"]) stack.push(...(Array.isArray(x["@graph"]) ? x["@graph"] : [x["@graph"]]));
        out.push(x);
      }
    }
  }
  return out;
}
function offersOf(items) {
  const out = [];
  const add = o => { for (const x of Array.isArray(o) ? o : [o]) if (x && typeof x === "object") out.push(x); };
  for (const it of items) { add(it.offers || []); for (const hv of it.hasVariant || []) add(hv.offers || []); }
  return out;
}
function num(x) {
  if (typeof x === "number") return x;
  let s = String(x).replace(/[^\d,.\-]/g, "");
  if (s.includes(",") && s.includes(".")) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (s.includes(",")) s = s.replace(",", ".");
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : null;
}
export function gtinOk(code) {
  const d = String(code).replace(/\s/g, "");
  if (!/^\d+$/.test(d) || ![8, 12, 13, 14].includes(d.length)) return false;
  const body = [...d.slice(0, -1)].map(Number).reverse();
  const total = body.reduce((a, x, i) => a + x * (i % 2 === 0 ? 3 : 1), 0);
  return (10 - total % 10) % 10 === Number(d.at(-1));
}
export function cvrOk(d) {
  return /^\d{8}$/.test(d || "") && [...d].reduce((a, c, i) => a + Number(c) * [2, 7, 6, 5, 4, 3, 2, 1][i], 0) % 11 === 0;
}
function noindex(h) {
  for (const t of (h || "").slice(0, 200_000).match(/<meta\b[^>]*>/gi) || [])
    if (/name=["']?(?:robots|googlebot)\b/i.test(t) && /content=["'][^"']*noindex/i.test(t)) return t.slice(0, 120);
  return null;
}

class Robots {
  constructor(txt) {
    const groups = []; let agents = [], rules = [], inRules = false;
    for (const raw of (txt || "").split(/\r?\n/)) {
      const line = raw.split("#")[0].trim(); const i = line.indexOf(":");
      if (i < 0) continue;
      const k = line.slice(0, i).trim().toLowerCase(), v = line.slice(i + 1).trim();
      if (k === "user-agent") { if (inRules) { groups.push([agents, rules]); agents = []; rules = []; inRules = false; } agents.push(v.toLowerCase()); }
      else if (k === "allow" || k === "disallow") { inRules = true; if (v) rules.push([k === "allow", v]); }
    }
    groups.push([agents, rules]);
    const mine = groups.filter(([a]) => a.some(x => x.includes("gmc-doktor"))).map(g => g[1]);
    const star = groups.filter(([a]) => a.includes("*")).map(g => g[1]);
    this.rules = (mine.length ? mine : star).flat();
  }
  allowed(path) {
    let bestLen = -1, bestAllow = true;
    for (const [allow, pat] of this.rules) {
      let rx = "^" + pat.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
      if (rx.endsWith("\\$")) rx = rx.slice(0, -2) + "$";
      let ok = false;
      try { ok = new RegExp(rx).test(path); } catch { continue; }
      const n = ok ? pat.length : -1;
      if (n > bestLen || (n === bestLen && n >= 0 && allow)) { bestLen = n; bestAllow = allow; }
    }
    return bestLen >= 0 ? bestAllow : true;
  }
}

class Fetcher {
  constructor(domain) { this.domain = domain; this.base = "https://" + domain; this.n = 0; this.log = []; this.robots = new Robots(""); }
  async init() { const [st, , , txt] = await this.raw("/robots.txt"); this.robots = new Robots(st === 200 ? txt : ""); }
  async raw(path) {
    this.n++;
    try {
      const r = await fetch(this.base + path, {headers: {"user-agent": UA, "accept-language": "da-DK,da;q=0.9,en;q=0.5"},
        redirect: "follow", signal: AbortSignal.timeout(9000), cf: {cacheTtl: 300}});
      let body = await r.text();
      if (body.length > MAX_BODY) body = body.slice(0, MAX_BODY);
      this.log.push([path, r.status]);
      return [r.status, r.url || this.base + path, r.headers, body];
    } catch (e) {
      this.log.push([path, null]);
      return [null, this.base + path, new Headers(), ""];
    }
  }
  async get(path) {
    if (!this.robots.allowed(path)) { this.log.push([path, "robots"]); return ["robots", this.base + path, new Headers(), ""]; }
    if (this.n >= MAX_REQ) return ["cap", this.base + path, new Headers(), ""];
    return this.raw(path);
  }
}

const chk = (id, sev, s, hvad, ret) => ({id, sev, s, t: PROBLEM[id] || id, hvad, ret});

export async function run(domain) {
  const f = new Fetcher(domain);
  await f.init();
  const res = {shop: domain, version: VERSION, checked: new Date().toISOString(), shopify: false, reachable: false, fund: [], n_ok: 0};
  const C = [], ok = id => { res.n_ok++; };
  let [st, final, hdr, home] = await f.get("/");
  if (st !== 200) { res.error = st === "robots" ? "robots" : "unreachable"; return res; }
  res.reachable = true;
  res.shopify = !!(hdr.get("x-shopid") || /shopify/i.test((hdr.get("powered-by") || "") + (hdr.get("server") || ""))
    || home.includes("cdn.shopify.com") || home.includes("Shopify.theme") || home.includes("/cdn/shop/"));
  const password = final.includes("/password") || home.includes("template-password");
  const L = links(home), homeTxt = text(home);
  const hrefs = L.map(([h, l]) => pathOf(h) + " " + l).join(" "), labels = L.map(([, l]) => l).join(" ");

  // contact/about pages + products.json in parallel
  const cand = [];
  for (const [href, label] of L) {
    let p = pathOf(href);
    if (p.includes("/pages/") && (/(kontakt|contact|kundeservice|customer-service|om-os|omos|om-mig|om-butikken|about|hvem|virksomhed|impressum|info)/i.test(p + " " + label)
        || /\/pages\/om(?:[-?]|$)/.test(p) || /^\s*om( os| mig| butikken)?\s*$/i.test(label))) {
      p = p.split("?")[0];
      if (!cand.includes(p)) cand.push(p);
    }
  }
  const pagePaths = cand.length ? cand.slice(0, 2) : ["/pages/kontakt", "/pages/contact"];
  const [pageRes, prodRes] = await Promise.all([Promise.all(pagePaths.map(p => f.get(p))), f.get("/products.json?limit=100")]);
  const seen = [];
  let pageTxt = "";
  pageRes.forEach(([s2, , , b2], i) => { if (s2 === 200) { pageTxt += " " + text(b2); seen.push(pagePaths[i]); } });
  const allTxt = homeTxt + " " + pageTxt;
  let products = [];
  if (prodRes[0] === 200) { try { products = JSON.parse(prodRes[3]).products || []; } catch { products = []; } }
  res.n_products = products.length;

  // 2 product pages + .js, in parallel
  const pp = (await Promise.all(products.filter(p => p.handle).slice(0, 2).map(async prod => {
    const [s4, final4, , b4] = await f.get(`/products/${prod.handle}`);
    if (s4 !== 200) return null;
    const [s5, , , b5] = await f.get(new URL(final4).pathname.replace(/\/$/, "") + ".js");
    let js = null;
    if (s5 === 200) { try { js = JSON.parse(b5); } catch { js = null; } }
    return [prod, b4, js];
  }))).filter(Boolean);

  if (password) C.push(chk("M01", "kritisk", "fejl", final, "Fjern adgangskoden under Onlinebutik → Præferencer, når butikken er klar."));

  // identity & contact
  const polFound = {};
  for (const [k, [pol, kw]] of Object.entries(POLICY_KEYS)) {
    const m = hrefs.match(pol) || hrefs.match(new RegExp("/pages/\\S*" + kw, "i")) || labels.match(new RegExp(kw, "i"));
    polFound[k] = m ? m[0].slice(0, 80) : null;
  }
  const hasTerms = !!polFound.terms;
  const where = seen.length ? "forsiden og kontakt-/om os-siden" : "forsiden";
  const notSeen = hasTerms ? "advarsel" : "fejl";
  const hint = hasTerms ? " Det kan stå i handelsbetingelserne." : "";
  const cvr = allTxt.match(CVR);
  if (cvr) ok(); else C.push(chk("C01", "kritisk", notSeen, `Ikke fundet på ${where}.${hint}`, "Skriv firmanavn og CVR-nummer i footeren på alle sider."));
  let addr = null;
  for (const sm of allTxt.matchAll(STREET)) {
    const pc = allTxt.slice(sm.index + sm[0].length, sm.index + sm[0].length + 80).match(POSTCODE_CITY);
    if (pc) { addr = sm[0] + ", " + pc[0]; break; }
  }
  if (addr) ok(); else C.push(chk("C02", "kritisk", notSeen, `Ingen fuld adresse (vej, nr., postnr. og by) fundet på ${where}.${hint}`, "Skriv fuld adresse i footeren og på kontaktsiden."));
  const mail = (allTxt.match(EMAIL) || []).find(m => !JUNK_MAIL.some(j => m.toLowerCase().includes(j)));
  const free = !!(mail && FREE_MAIL.some(x => mail.split("@")[1].toLowerCase().startsWith(x)));
  if (mail && !free) ok();
  else C.push(mail ? {...chk("C04", "høj", "advarsel", `${mail} (gratis mailudbyder)`, "Brug en mail på butikkens eget domæne."), t: "Kontaktmailen er en gratis mailadresse (fx Gmail)"}
    : chk("C04", "høj", notSeen, `Ingen e-mailadresse fundet på ${where}.${hint}`, "Vis en e-mail på butikkens eget domæne i footeren og på kontaktsiden."));
  const cvrDigits = cvr ? cvr[1].replace(/\D/g, "") : null;
  if (cvr && /CVR/i.test(cvr[0]) && !cvrOk(cvrDigits))
    C.push(chk("C06", "høj", "fejl", `fx '${cvr[0].trim()}' består ikke CVR-registrets kontrol.`, "Ret CVR-nummeret, så det passer med virk.dk."));
  let phone = null;
  for (const m of allTxt.matchAll(PHONE)) {
    const s = m[0].trim();
    if (cvrDigits && s.replace(/\D/g, "").slice(-8) === cvrDigits) continue;
    if (s.startsWith("+45") || PHONE_CTX.test(allTxt.slice(Math.max(0, m.index - 40), m.index))) { phone = s; break; }
  }
  if (phone) ok(); else C.push(chk("C03", "middel", "advarsel", `Intet telefonnummer fundet på ${where}.`, "Vis et telefonnummer i footeren eller på kontaktsiden."));
  if (seen.length) ok(); else C.push(chk("C05", "middel", "fejl", "Ingen kontakt- eller om os-side fundet via forsidens links.", "Lav en side med firmanavn, adresse, CVR, telefon og mail, og link til den fra menu og footer."));

  // policies
  const pol = {returns: ["P01", "kritisk"], shipping: ["P02", "høj"], terms: ["P03", "høj"], privacy: ["P04", "middel"]};
  const helpLink = labels.match(HELP_LINK);
  for (const [k, [id, sev]] of Object.entries(pol)) {
    if (polFound[k]) { ok(); continue; }
    if ((k === "returns" || k === "shipping") && hasTerms) C.push(chk(id, sev, "advarsel", "Intet direkte link; oplysningerne står måske i handelsbetingelserne.", "Link direkte til politikken i footeren."));
    else if (helpLink) C.push(chk(id, sev, "advarsel", `Intet direkte link; kun et '${helpLink[0]}'-link, hvor oplysningerne måske står.`, "Link direkte til politikken i footeren."));
    else C.push(chk(id, sev, "fejl", "Intet link fundet på forsiden.", "Udfyld politikken og link til den i footeren."));
  }

  // product data
  if (products.length) {
    const n = products.length;
    const zero = products.filter(p => (p.variants || []).some(v => Number(v.price || 0) === 0)).map(p => p.title);
    if (zero.length) C.push(chk("D02", "høj", "fejl", `${zero.length} varer med pris 0, fx '${zero[0].slice(0, 60)}'`, "Sæt en rigtig pris, eller fjern varen fra Google-kanalen.")); else ok();
    const badT = products.filter(p => (p.title || "").length > 150 || ((p.title || "") === (p.title || "").toUpperCase() && /[A-ZÆØÅ]/.test(p.title) && p.title.length > 8) || SALES_WORDS.test(p.title || "")).map(p => p.title);
    if (badT.length) C.push(chk("D04", "middel", "advarsel", `${badT.length} titler, fx '${badT[0].slice(0, 70)}'`, "Skriv titler som 'Mærke + produkttype + egenskab', uden salgsord.")); else ok();
    const noimg = products.filter(p => !(p.images || []).length).map(p => p.title);
    if (noimg.length) C.push(chk("D05", "høj", "fejl", `${noimg.length} varer uden billede, fx '${noimg[0].slice(0, 60)}'`, "Tilføj mindst ét tydeligt produktbillede.")); else ok();
    const notype = products.filter(p => !String(p.product_type || "").trim()).length;
    if (notype > n / 2) C.push(chk("D06", "lav", "advarsel", `${notype} af ${n} varer mangler produkttype.`, "Udfyld 'Produkttype' på varerne (fx 'Plaid', 'Kokkekniv').")); else ok();
    const big = products.filter(p => (p.variants || []).some(v => { const pr = Number(v.price || 0), cp = Number(v.compare_at_price || 0); return pr > 0 && cp > 2 * pr; })).map(p => p.title);
    if (big.length >= 3) C.push(chk("D07", "middel", "advarsel", `${big.length} varer med førpris over 2× salgspris, fx '${big[0].slice(0, 60)}'`, "Fjern 'sammenlign ved'-priser, der ikke er reelle tidligere priser.")); else ok();
    const nodesc = products.filter(p => text(p.body_html || "").length < 20).map(p => p.title);
    if (nodesc.length) C.push(chk("D08", "høj", nodesc.length >= 3 || nodesc.length >= n * 0.1 ? "fejl" : "advarsel", `${nodesc.length} af ${n} varer har ingen beskrivelse, fx '${nodesc[0].slice(0, 60)}'`, "Skriv 2-4 sætninger om varen: hvad det er, materiale, mål og brug.")); else ok();
    const tiny = [], small = [];
    for (const p of products) {
      const im = (p.images || [])[0];
      if (!im || !im.width || !im.height) continue;
      const side = Math.min(im.width, im.height);
      if (side < 100) tiny.push(p.title); else if (side < 500) small.push(p.title);
    }
    if (tiny.length) C.push(chk("D09", "høj", "fejl", `${tiny.length} varer har et hovedbillede under 100 px, fx '${tiny[0].slice(0, 60)}'`, "Upload produktbilleder på mindst 800 × 800 px."));
    else if (small.length >= 3) C.push(chk("D09", "middel", "advarsel", `${small.length} varer har et hovedbillede under 500 px, fx '${small[0].slice(0, 60)}'`, "Upload produktbilleder på mindst 800 × 800 px."));
    else ok();
    const demoP = products.filter(p => DEMO_PRODUCT.test((p.title || "") + " " + text(p.body_html || ""))).map(p => p.title);
    if (demoP.length) C.push(chk("D11", "høj", "fejl", `${demoP.length} varer med demo- eller fyldtekst, fx '${demoP[0].slice(0, 60)}'`, "Slet demo-varerne, eller skriv rigtige titler og beskrivelser."));
    const sold = products.filter(p => (p.variants || []).length && !p.variants.some(v => v.available)).map(p => p.title);
    if (n >= 10 && sold.length >= n / 2) C.push(chk("D12", "lav", "advarsel", `${sold.length} af ${n} varer er udsolgt, fx '${sold[0].slice(0, 60)}'`, "Skjul udsolgte varer, der ikke kommer igen."));
    if (n < 3) C.push(chk("M04", "høj", "fejl", `Kun ${n} varer fundet.`, "Tilføj flere varer, eller vent med Google Shopping."));
  }

  // GTIN + structured data on sampled product pages
  if (pp.length) {
    const jsVars = pp.flatMap(([, , js]) => (js && js.variants) || []);
    if (jsVars.length) {
      const share = jsVars.filter(v => !String(v.barcode || "").trim()).length / jsVars.length;
      if (share > 0.5) C.push(chk("D03", "middel", "advarsel", `${Math.round(share * 100)} % af ${jsVars.length} varianter på ${pp.length} stikprøvevarer mangler stregkode.`, "Udfyld GTIN for mærkevarer, eller marker 'ingen GTIN' for egne produkter.")); else ok();
      const badG = jsVars.filter(v => String(v.barcode || "").trim() && !gtinOk(v.barcode));
      if (badG.length) C.push(chk("D10", "høj", "fejl", `${badG.length} af ${jsVars.length} varianter har en ugyldig stregkode, fx '${String(badG[0].name || badG[0].title || "").slice(0, 50)}' med stregkoden ${String(badG[0].barcode).trim()}`, "Ret stregkoden til producentens rigtige EAN, eller fjern den."));
    }
    const noLd = [], mism = [], availBad = [], comma = [], curBad = [], ldGap = [];
    for (const [prod, b, js] of pp) {
      const items = ldjson(b).filter(x => ["product", "productgroup"].includes(String(x["@type"] || "").toLowerCase()));
      if (!items.length) { if (!/itemtype=["']https?:\/\/schema\.org\/Product["']/i.test(b)) noLd.push(prod.title); continue; }
      const offers = offersOf(items);
      const shopCur = b.match(/Shopify\.currency\s*=\s*\{"active":"([A-Z]{3})"/);
      const ldCur = new Set(offers.filter(o => o.priceCurrency).map(o => String(o.priceCurrency).toUpperCase()));
      if (shopCur && ldCur.size && !ldCur.has(shopCur[1])) curBad.push(`${prod.title.slice(0, 40)}: ${[...ldCur].join(", ")} i stedet for ${shopCur[1]}`);
      const raw = offers.map(o => o.price).filter(p => p !== undefined && p !== null && p !== "");
      const missing = [["billede", items.some(it => it.image)], ["pris", raw.length > 0]].filter(([, okk]) => !okk).map(([w]) => w);
      if (missing.length) ldGap.push(`${prod.title.slice(0, 40)}: mangler ${missing.join(" og ")}`);
      const cp = raw.find(p => typeof p === "string" && p.includes(","));
      if (cp) comma.push(`${prod.title.slice(0, 40)}: '${cp}'`);
      const ldP = new Set(raw.map(num).filter(v => v !== null).map(v => Math.round(v * 100)));
      if (js && ldP.size) {
        const jsP = new Set((js.variants || []).map(v => Number(v.price || 0)));
        if (jsP.size && ![...ldP].some(x => jsP.has(x))) mism.push(`${prod.title.slice(0, 40)}: strukturerede data ${[...ldP].slice(0, 2).map(x => x / 100).join(", ")} vs. butikkens pris ${[...jsP].slice(0, 2).map(x => x / 100).join(", ")}`);
        const ldAv = new Set(offers.map(o => String(o.availability || "").split("/").pop().toLowerCase()));
        const jsAv = (js.variants || []).some(v => v.available);
        if (ldAv.size && ldAv.has("instock") !== jsAv) availBad.push(prod.title.slice(0, 40));
      }
    }
    if (noLd.length) C.push(chk("S01", "middel", "advarsel", `Mangler på ${noLd.length} af ${pp.length} tjekkede sider`, "Brug et tema eller en app, der udsender Product-data (JSON-LD).")); else ok();
    if (mism.length) C.push(chk("S02", "høj", "fejl", mism.slice(0, 2).join("; "), "Sørg for, at temaet udsender samme pris som den viste pris.")); else ok();
    if (comma.length) C.push(chk("S05", "middel", "advarsel", comma.slice(0, 2).join("; "), "Ret temaets JSON-LD, så prisen skrives med punktum (fx 349.00)."));
    if (curBad.length) C.push(chk("S06", "høj", "fejl", curBad.slice(0, 2).join("; "), "Ret temaets JSON-LD, så priceCurrency er butikkens valuta."));
    if (ldGap.length) C.push(chk("S07", "middel", "fejl", ldGap.slice(0, 2).join("; "), "Ret temaets JSON-LD, så hver vare har image, price og priceCurrency."));
    if (availBad.length) C.push(chk("S03", "middel", "advarsel", availBad.slice(0, 3).join(", "), "Lad udsolgte varer markeres som udsolgt i produktdataene.")); else ok();
  }

  // trust & red flags
  let scar = homeTxt.match(SCARCITY);
  for (const [, b] of pp) scar = scar || text(b).match(SCARCITY);
  const timer = home.match(TIMER_APPS) || pp.map(([, b]) => b.match(TIMER_APPS)).find(Boolean);
  const hit = (scar && scar[0]) || (timer && timer[0]) || "";
  if (hit) C.push(chk("M02", "middel", "advarsel", `Fundet: '${hit}'`, "Fjern nedtællings- og knaphedsapps, medmindre tallene er ægte.")); else ok();
  const demo = homeTxt.match(DEMO);
  if (demo) C.push(chk("M05", "høj", "fejl", `fx '${demo[0]}'`, "Erstat temaets eksempeltekster med jeres egne tekster."));
  const years = [...homeTxt.matchAll(COPYRIGHT)].map(m => Number(m[1]));
  if (years.length && Math.max(...years) <= new Date().getUTCFullYear() - 2) C.push(chk("M06", "lav", "advarsel", `Footeren siger © ${Math.max(...years)}.`, "Brug temaets automatiske årstal."));
  const tm = home.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = tm ? unescape(tm[1].replace(/\s+/g, " ")).trim() : "";
  const desc = (home.slice(0, 200_000).match(/<meta\b[^>]*>/gi) || []).some(t => /name=["']description["']/i.test(t) && /content=["'][^"']{20,}/i.test(t));
  const generic = GENERIC_TITLE.test(title);
  if (generic || !desc) C.push(chk("M09", "lav", "advarsel", generic ? `Forsidens titel er '${title || "tom"}'.` : "Forsiden har ingen beskrivelse (meta description).", "Skriv en titel og beskrivelse under Onlinebutik → Præferencer."));
  const hi = home.match(HTTP_IMG);
  if (hi) C.push(chk("M10", "lav", "advarsel", `fx ${hi[0].slice(-80)}`, "Upload billedet til Shopify og brug det nye link."));
  const ni = noindex(home);
  if (ni) C.push(chk("M07", "høj", "fejl", `Forsiden har et 'noindex'-tag: ${ni}`, "Fjern 'noindex' fra temaet eller den app, der sætter det."));
  if (final.startsWith("http://")) C.push(chk("M08", "høj", "fejl", final, "Slå SSL til for domænet, så alle sider sender videre til https."));
  if (final.includes(".myshopify.com")) C.push(chk("M03", "middel", "fejl", final, "Tilknyt et eget domæne som primært domæne.")); else ok();

  // score + order: errors by severity, then concrete warnings, then the rest
  let pen = 0;
  for (const c of C) pen += c.s === "fejl" ? PENALTY[c.sev] : PENALTY[c.sev] / 2;
  res.score = Math.max(0, Math.round(100 - pen));
  const rank = c => (c.s === "fejl" ? 0 : CONCRETE.has(c.id) ? 10 : 20) + SEV[c.sev];
  res.fund = C.sort((a, b) => rank(a) - rank(b));
  res.n_fejl = C.filter(c => c.s === "fejl").length;
  res.n_adv = C.length - res.n_fejl;
  res.requests = f.n;
  return res;
}
