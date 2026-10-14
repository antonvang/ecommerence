// Webshopdoktoren: the sign-up form on webshopdoktoren.dk posts here, and the request is mailed to the company's Gmail
// (a verified Email Routing destination). GET /api/tjek runs the instant store check (tjek.js) for the field on the page.
// Runs as the Cloudflare Worker "henvendelse" on webshopdoktoren.dk/api/*.
import { EmailMessage } from "cloudflare:email";
import { run, VERSION } from "./tjek.js";

const TO = "webshopdoktoren.dk@gmail.com";
const FROM = "formular@webshopdoktoren.dk";
const MAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const SHOP_RE = /^[^\s@/]+\.[a-z]{2,}(\/\S*)?$/i;

const json = (o, status = 200) => new Response(JSON.stringify(o), {status, headers: {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}});
const clean = (v, n = 200) => String(v ?? "").replace(/[\r\n\t]+/g, " ").trim().slice(0, n);
const b64 = s => { let t = ""; for (const x of new TextEncoder().encode(s)) t += String.fromCharCode(x); return btoa(t); };
const HOST_RE = /^(?=.{4,253}$)(?:[a-z0-9æøåäöü](?:[a-z0-9æøåäöü-]*[a-z0-9æøåäöü])?\.)+[a-z]{2,}$/i;
const hostOf = v => clean(v).toLowerCase().replace(/^https?:\/\//, "").split(/[/?#]/)[0].replace(/:\d+$/, "").replace(/\.$/, "").replace(/^www\./, "");
const cacheKey = host => new Request(`https://webshopdoktoren.dk/__tjek/${VERSION}/${encodeURIComponent(host)}`);
const hits = new Map(); // per-isolate rate limit: enough checks for a person, too slow for scraping
function limited(ip) {
  const now = Date.now(), h = (hits.get(ip) || []).filter(t => now - t < 600_000);
  h.push(now);
  if (hits.size > 5000) hits.clear();
  hits.set(ip, h);
  return h.length > 8;
}

async function tjek(req, url, ctx) {
  const host = hostOf(url.searchParams.get("shop"));
  if (!HOST_RE.test(host) || /(^|\.)webshopdoktoren\.dk$/.test(host))
    return json({ok: false, error: "Skriv jeres webshops adresse, fx dinbutik.dk."}, 400);
  const key = cacheKey(host);
  const hit = await caches.default.match(key);
  if (hit) return json({ok: true, ...(await hit.json()), cached: true});
  if (limited(req.headers.get("cf-connecting-ip") || "?")) return json({ok: false, error: "Du har tjekket mange butikker på kort tid. Prøv igen om 10 minutter."}, 429);
  let r;
  try { r = await run(host); } catch (e) { return json({ok: false, error: "Tjekket gik galt. Prøv igen om lidt."}, 502); }
  // the page shows what is wrong; how to fix it is what customers pay for, so it never leaves the server
  r.fund = (r.fund || []).map(({ret, ...f}) => f);
  if (r.error === "robots") return json({ok: false, error: "Butikken beder robotter om ikke at læse forsiden. Skriv jeres mail nedenfor, så kigger vi selv."});
  if (r.error) return json({ok: false, error: `Vi kunne ikke åbne ${host}. Tjek adressen, eller skriv jeres mail nedenfor, så kigger vi selv.`});
  ctx.waitUntil(caches.default.put(key, new Response(JSON.stringify(r), {headers: {"content-type": "application/json", "cache-control": "max-age=21600"}})));
  return json({ok: true, ...r});
}

async function cachedResult(shop) {
  try {
    const hit = await caches.default.match(cacheKey(hostOf(shop)));
    return hit ? await hit.json() : null;
  } catch { return null; }
}
const fundLines = r => r ? [`Tjekket på siden: score ${r.score}, ${r.n_fejl} fejl, ${r.n_adv} advarsler`,
  ...r.fund.slice(0, 8).map(f => `- ${f.s === "fejl" ? "Fejl" : "Advarsel"}: ${f.t} (${f.hvad})`), ""] : [];

// the confirmation the customer gets right away (Cloudflare Email Sending, binding EMAIL); without it the form still works
const SENDER = {email: "info@webshopdoktoren.dk", name: "Webshopdoktoren"};
const escHtml = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
async function confirmCustomer(env, {shop, mail, navn, onsker, r}) {
  if (!env.EMAIL || !mail) return false;
  const fn = (navn.split(/\s+/)[0] || "").replace(/[^\p{L}-]/gu, "");
  const lead = {
    ret: [`I vil gerne have os til at rette fejlene i ${shop}.`, "Vi kontakter jer i dag og aftaler det praktiske. Prisen er 995 kr., og I betaler først, når det er rettet."],
    vejledning: [`I vil gerne have vores trin-for-trin-vejledning til ${shop} (495 kr.).`, "Vi vender tilbage i dag."],
    rapport: [`Vi har fået jeres henvendelse om et gratis tjek af ${shop}.`, "Vi går i gang med det samme og sender den fulde rapport til denne mail i dag. Den fortæller, hvad vi fandt, og hvordan I retter det."],
  }[onsker];
  const found = r && r.fund && r.fund.length ? r.fund.slice(0, 3).map(f => f.t) : [];
  const sig = ["Venlig hilsen", "Anton Vangsgaard", "Webshopdoktoren", "info@webshopdoktoren.dk", "webshopdoktoren.dk"];
  const text = [fn ? `Hej ${fn},` : "Hej,", "Tak for jeres henvendelse.", ...lead,
    ...(found.length ? ["Det hurtige tjek på siden fandt blandt andet:\n" + found.map(t => `- ${t}`).join("\n")] : []),
    "Har I spørgsmål imens, så svar bare på denne mail.", sig.join("\n"),
    "I får denne mail, fordi I har skrevet til os på webshopdoktoren.dk."].join("\n\n");
  const p = t => `<p style="margin:0 0 14px">${t}</p>`;
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.55;color:#0f1a14;max-width:560px">`
    + p(fn ? `Hej ${escHtml(fn)},` : "Hej,") + p("Tak for jeres henvendelse.") + lead.map(t => p(escHtml(t))).join("")
    + (found.length ? p("Det hurtige tjek på siden fandt blandt andet:") + `<ul style="margin:0 0 14px;padding-left:20px">${found.map(t => `<li>${escHtml(t)}</li>`).join("")}</ul>` : "")
    + p("Har I spørgsmål imens, så svar bare på denne mail.")
    + `<p style="margin:22px 0 0">Venlig hilsen<br><b>Anton Vangsgaard</b><br>Webshopdoktoren<br><a href="mailto:info@webshopdoktoren.dk" style="color:#0b6b4f">info@webshopdoktoren.dk</a> · <a href="https://webshopdoktoren.dk" style="color:#0b6b4f">webshopdoktoren.dk</a></p>`
    + `<p style="margin:22px 0 0;font-size:12px;color:#66736c">I får denne mail, fordi I har skrevet til os på webshopdoktoren.dk.</p></div>`;
  try {
    await env.EMAIL.send({to: mail, from: SENDER, replyTo: SENDER, subject: `Vi har fået jeres henvendelse: ${shop}`, text, html});
    return true;
  } catch (e) { return false; }
}
const formHits = new Map(); // the form also sends a mail to whatever address is typed in: keep it to a person's pace
function formLimited(ip) {
  const now = Date.now(), h = (formHits.get(ip) || []).filter(t => now - t < 600_000);
  h.push(now);
  if (formHits.size > 5000) formHits.clear();
  formHits.set(ip, h);
  return h.length > 5;
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (url.pathname === "/api/tjek") return req.method === "GET" ? tjek(req, url, ctx) : json({ok: false, error: "Brug GET."}, 405);
    if (url.pathname !== "/api/henvendelse") return new Response("Not found", {status: 404});
    if (req.method !== "POST") return json({ok: false, error: "Brug formularen på webshopdoktoren.dk."}, 405);
    let d;
    try { d = await req.json(); } catch { return json({ok: false, error: "Formularen kunne ikke læses. Prøv igen."}, 400); }
    if (clean(d.hp)) return json({ok: true}); // honeypot: bots fill it in, people never see it
    const shop = clean(d.shop).replace(/^https?:\/\//i, "").replace(/\/+$/, "").toLowerCase();
    const mail0 = clean(d.mail).toLowerCase(), mail = MAIL_RE.test(mail0) ? mail0 : "", navn = clean(d.navn, 100), tlf = clean(d.tlf, 40);
    const WANT = {rapport: "Gratis rapport", vejledning: "Trin-for-trin-vejledning (495 kr.)", ret: "Vil have fejlene rettet (995 kr.)"};
    const onsker = WANT[clean(d.onsker, 20)] ? clean(d.onsker, 20) : "rapport";
    if (!SHOP_RE.test(shop)) return json({ok: false, field: "shop", error: "Skriv jeres webshops adresse, fx dinbutik.dk."}, 400);
    // a mail or a phone number is enough: the fewer fields, the more shops ask
    const okTlf = /^\+?\d{8,15}$/.test(tlf.replace(/[\s().-]/g, ""));
    if (!mail && !okTlf) return json({ok: false, field: "kontakt", error: "Skriv jeres mail eller telefonnummer, så vi kan svare jer."}, 400);
    if (formLimited(req.headers.get("cf-connecting-ip") || "?")) return json({ok: false, error: "Vi har fået flere henvendelser fra jer på kort tid. Skriv til info@webshopdoktoren.dk, hvis noget mangler."}, 429);
    const r = await cachedResult(shop);
    const auto = !!(env.EMAIL && mail);
    const body = [`Webshop: ${shop}`, `Ønske: ${WANT[onsker]}`, `Navn: ${navn || "-"}`, `Telefon: ${tlf || "-"}`, `Mail: ${mail || "-"}`,
      // the dashboard reads this line and stops offering 'Send bekræftelse'
      ...(auto ? [`Bekræftelse: sendt automatisk til ${mail}`] : []), "",
      ...fundLines(r),
      mail ? "Sendt fra formularen på webshopdoktoren.dk. Svar på denne mail for at skrive til kunden." : "Sendt fra formularen på webshopdoktoren.dk. Kunden har kun skrevet et telefonnummer: ring op."].join("\r\n");
    // the subject keeps 'Gratis tjek:' first, so the dashboard's Gmail search still finds it
    const subject = `Gratis tjek: ${shop}` + (onsker === "ret" ? " · vil have det rettet" : onsker === "vejledning" ? " · vil have vejledningen" : "") + (mail ? "" : " · ring op");
    try { await env.MAILER.send(internal(subject, body, mail)); }
    catch (e) { return json({ok: false, error: "Det gik ikke lige nu. Prøv igen om lidt, eller skriv til info@webshopdoktoren.dk."}, 502); }
    let bekraeftet = false;
    if (auto) {
      bekraeftet = await confirmCustomer(env, {shop, mail, navn, onsker, r});
      if (!bekraeftet) ctx.waitUntil(env.MAILER.send(internal(`Bekræftelsen kunne ikke sendes: ${shop}`,
        `Den automatiske bekræftelse til ${mail} kunne ikke sendes. Send den fra dashboardet under Henvendelser.`, mail)).catch(() => {}));
    }
    return json({ok: true, bekraeftet});
  },
};

function internal(subject, body, replyTo) {
  return new EmailMessage(FROM, TO, [
    `From: Webshopdoktoren formular <${FROM}>`,
    `To: <${TO}>`,
    ...(replyTo ? [`Reply-To: <${replyTo}>`] : []),
    `Subject: =?UTF-8?B?${b64(subject)}?=`,
    `Message-ID: <${crypto.randomUUID()}@webshopdoktoren.dk>`,
    `Date: ${new Date().toUTCString()}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    b64(body).replace(/.{1,76}/g, "$&\r\n").trim(),
  ].join("\r\n"));
}
