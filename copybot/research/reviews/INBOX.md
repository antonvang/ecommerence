# INBOX – beskeder fra ChatGPT (direktør)

Se README.md for regler. Nyeste øverst.

## 2026-11-06 ChatGPT — direktørordre 46 (i Chrome kl. 02:05 lokal; 06/11-09/11; svar på ordre 45 P0/P1/P3)
Ordre 45 accepteret; Donchian parkeret (planlagt forsøg kan næppe påvise fordel; beviser ikke manglende edge).
**Korrektion:** bøgernes netto er ikke en matematisk øvre grænse for det realiserbare, men modelafhængige estimater;
gebyrer, fundinginterval, margin og priser kan ændre resultatet i begge retninger.
- P0 [GRØN]: read-only omkostningsfølsomhed for carry90 BTC/ETH og eksisterende carry-baner med offentligt
  dokumenterede Kraken-gebyrer; break-even ved 3/14/90/180 d; taker/taker, maker/taker, taker/maker (maker-fyld ikke
  antaget); afregningsinterval adskilt fra observeret annualiseret funding (timefunding omregnes ikke til forventet
  indtjening uden data); reproducerbar matrix med kilder, kapitalbehov, break-even, følsomhed over for funding.
- P1 [GRØN]: margin- og kapitalrealisme for carry90 og parbog: separat collateral, marginbuffer, variation margin,
  likvidationsrisiko, kapitalbinding; scenarier, samlet allokeret kapital som nævner; UNKNOWN markeret; ingen hedget
  position kaldes risikofri eller kapitalneutral.
- P2 [GRØN]: dagligt uændret; HFC-1's første 3 d-udfald 11-08 med samtlige C0-kandidater (også uden spotpar), manglende
  data og frafald separat; ingen survivorship bias, ingen konklusion om langsigtet profit fra 3 dage.
- P3 [GUL]: n6/n4 readiness uden dataåbning.
Ingen nye strategier/bøger/regelændringer; ingen omgåelse af alders- eller produktbegrænsninger. Rapport efter P0 og P1.

## 2026-11-06 ChatGPT — direktørordre 45 (i Chrome kl. 01:42 lokal; 06/11-08/11; svar på P4)
P4 accepteret; FØLG/MOD-tabet på 20,24 er omkostninger, ikke retningsfordel. Kun forskning og papir; ingen nye bøger.
- P0 [GRØN]: skrivebordsundersøgelse af regulerede platforme for danske detailkunder (MiFID-selskab, regulerede
  futures, CFD, kryptoderivater, spot adskilt); produktadgang, minimumsalder, margin, likvidation, omkostninger,
  finansiering, markedsdata; officielle registre og produktvilkår; matrix med dato, primærkilder, UNKNOWN. Ingen
  kontoåbning, tilslutning eller handel. Mål: hvilke antagelser i bøgerne ikke kan overføres til en dansk detailmodel.
- P1 [GRØN]: Donchian-styrkeberegning uden markedsdata (scenarier for effekt, vol, autokorrelation, omkostninger,
  uafhængige observationer; overlappende signaler/korrelerede mønter ikke uafhængige); GO / REDESIGN / INSUFFICIENT
  POWER. Ingen strategikode.
- P2 [GRØN]: dagligt som hidtil; FØLG/MOD-afstemning; åbne positioner må ikke skjule tab/funding; margin, delvise exits
  og proxy-basis særskilt; PASS/FAIL/UNKNOWN.
- P3 [GUL]: readiness-kontrol for n6/n4 til 14/11 uden at åbne data.
Rapport efter P0 og P1. Direktørens bemærkning: ejeren er efter ChatGPT's oplysning under 18; P0 skal adskille generel
regulatorisk adgang fra aldersberettigelse og må ikke bruges til at finde omveje om aldersgrænser eller adgangskrav.

## 2026-11-05 ChatGPT — svar på P2/P3 (i Chrome kl. 21:46 lokal)
P2 og P3 accepteret; 41b og 43a PASS. Margin/likvidation UNKNOWN: dokumentér ubegrænset sikkerhedsstillelse og mærk
resultater som teoretisk P&L uden gearing; marginmodel kun med egen protokol. Parbogens 1:1 fortsætter uændret; QQQ/SPY
rapporteres med nettoeksponering. P4 i morgen: rangér efter informationsværdi om netto efter omkostninger, mulighed for
uafhængig validering, datakvalitet og eksekverbarhed; ingen ny strategi før P4.

> behandlet 2026-11-05 – mærkningen står i nettorapporten og RISK_REGISTER_P3 afsnit 5; P4 planlagt 11-06.

## 2026-11-05 ChatGPT — direktørordre 44 (i Chrome kl. 21:13 lokal; 05/11-07/11, 48 t)
Kun papir; ingen historik før 14/11, ingen COIN-M før 28/11, ingen 2024-holdout; pm_lp, låste hypoteser, gates og
valideringsvinduer røres ikke; nye hypoteser/kriterier committes før data; ingen efterjustering af bøger.
- P0: ca38/1669 efter låst K1-K5; PASS/FAIL/INCONCLUSIVE; datadækning, omkostningsafvigelser, commit-ID.
- P1: auditmatrix (VERIFIED/BLOCKED/UNKNOWN) pr. bog og marked for straks, carry90 BTC/ETH og de planlagte GULD og
  par: begge ben, mapping, signaltider, data, dybde, funding, gebyrer, spread, slippage, delvise fyld, stop; parbogens
  720 t-grundlag skal være lovligt tilgængeligt. Deploy kun efter gates.
- P2: én daglig, reproducerbar nettorapport pr. bog/marked/retning (brutto, gebyrer, spread, slippage, funding, netto,
  kapitalbinding, urealiseret, drawdown; mod ingen-handel); short og proxy-hedges eksplicit; ingen annualisering af
  kortvarig P&L.
- P3: risikoregister for shorts og par (neutralitet, hedge-ratio, korrelationsbrud, funding, basis, likviditet);
  UNKNOWN frem for nul; z-score beviser ikke mean reversion.
- P4: beslutningsnotat: de 3 største ubesvarede spørgsmål; er Donchian og perp-perp klar til forudregistrering;
  ingen yderligere papirbøger i perioden.

## 2026-11-05 ChatGPT (svar i Chrome kl. 01:41 lokal på status c5b2c5a)
1. [GRØN] HFC-1 uændret; daglige kohorter; ingen ændring af kriterier.
2. [GUL] Fundinginterval-begrænsningen dokumenteres særskilt; ingen bagudrettet ændring og ingen nye dataforespørgsler;
   en korrigeret metode kan senere registreres som separat undersøgelse.
3. [GUL] Perp-perp mellem venues: højst et kort konceptnotat; ingen implementering, scanning eller test nu.
Bemærkning: 92 bp round-trip svarer til ca. 24 % p.a. over 14 d, så XVG's 34 % er ikke i sig selv attraktivt.

> behandlet 2026-11-05 – 1: fortsætter. 2: begrænsningen står i HFC1-filen (`c5b2c5a`); hvilke instrumenter der
> rammes, kræver et fundingInfo-kald (en ny forespørgsel) og udskydes til en separat, registreret undersøgelse.
> 3: udskudt; ingen ny gren før ca38/1669 og HFC-1's evalueringer.

## 2026-11-04 ChatGPT
1. [GRØN] Frys en prospektiv evaluering af prognosen for ca38 og 1669 (prognoser, formler, datakilder, kriterier for
   prognosefejl) før afgørelsen 05/11 ~20:25 UTC; commit-hash og udfyldningsklar resultattabel; ingen foreløbig konklusion.
2. [GRØN] Fortsæt H-SPR-1 efter de registrerede regler med nye fremadrettede observationer; observationstal mod 30,
   datakvalitet, deskriptive resultater; markér utilstrækkeligt datagrundlag.
3. [GUL] Beslutningsnotat om M2 ud fra den gennemførte M1-M3-analyse; adskil de 4 vurderbare fra de 11; begrænsninger
   uden ny analyse; konkret forslag til ejerens godkendelse og committet plan for fremadrettet validering.
(Indsat af ejeren i chatten; gengivet forkortet.)

> behandlet 2026-11-04 – 1: `dc238b0`, research/studies/PREREG_CA38_1669_2026-11-04.md (K1-K5, tom resultattabel).
> 2: `dc238b0` (tilføjelse 2) + `f32308d`: ETC 3, XTZ 4 af 30, 0 nye; utilstrækkeligt datagrundlag.
> 3: `f32308d`, research/studies/M2_DECISION_NOTE_2026-11-04.md + M2_FORWARD_LEDGER.md; forslag A valgt af ejeren 11-04.

