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

async function cachedFund(shop) {
  try {
    const hit = await caches.default.match(cacheKey(hostOf(shop)));
    if (!hit) return [];
    const r = await hit.json();
    return [`Tjekket på siden: score ${r.score}, ${r.n_fejl} fejl, ${r.n_adv} advarsler`,
      ...r.fund.slice(0, 8).map(f => `- ${f.s === "fejl" ? "Fejl" : "Advarsel"}: ${f.t} (${f.hvad})`), ""];
  } catch { return []; }
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
    const body = [`Webshop: ${shop}`, `Ønske: ${WANT[onsker]}`, `Navn: ${navn || "-"}`, `Telefon: ${tlf || "-"}`, `Mail: ${mail || "-"}`, "",
      ...(await cachedFund(shop)),
      mail ? "Sendt fra formularen på webshopdoktoren.dk. Svar på denne mail for at skrive til kunden." : "Sendt fra formularen på webshopdoktoren.dk. Kunden har kun skrevet et telefonnummer: ring op."].join("\r\n");
    // the subject keeps 'Gratis tjek:' first, so the dashboard's Gmail search still finds it
    const subject = `Gratis tjek: ${shop}` + (onsker === "ret" ? " · vil have det rettet" : onsker === "vejledning" ? " · vil have vejledningen" : "") + (mail ? "" : " · ring op");
    const raw = [
      `From: Webshopdoktoren formular <${FROM}>`,
      `To: <${TO}>`,
      ...(mail ? [`Reply-To: <${mail}>`] : []),
      `Subject: =?UTF-8?B?${b64(subject)}?=`,
      `Message-ID: <${crypto.randomUUID()}@webshopdoktoren.dk>`,
      `Date: ${new Date().toUTCString()}`,
      "MIME-Version: 1.0",
      "Content-Type: text/plain; charset=UTF-8",
      "Content-Transfer-Encoding: base64",
      "",
      b64(body).replace(/.{1,76}/g, "$&\r\n").trim(),
    ].join("\r\n");
    try { await env.MAILER.send(new EmailMessage(FROM, TO, raw)); }
    catch (e) { return json({ok: false, error: "Det gik ikke lige nu. Prøv igen om lidt, eller skriv til info@webshopdoktoren.dk."}, 502); }
    return json({ok: true});
  },
};
