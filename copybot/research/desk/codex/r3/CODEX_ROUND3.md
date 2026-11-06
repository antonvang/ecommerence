# Codex-runde 3 — Mutation Lab, direktørordre 52 P0

## Resultat

45 isolerede mutanter blev fremstillet fra den SHA-256-verificerede frosne
Claude v1.1.1. 43 er ikke-ækvivalente fejl; M43 og M44 er beviseligt
ækvivalente omskrivninger og holdes uden for nævnerne.

| Fase | Sikkerhedskritiske | Øvrige ikke-ækvivalente | Overlevende |
| --- | ---: | ---: | --- |
| Før supplering | 28/28 = 100 % | 11/15 = 73,33 % | M23, M27, M41, M45 |
| Efter supplering | 28/28 = 100 % | 15/15 = 100 % | ingen |

Der var ingen sikkerhedskritiske overlevende i første fase. Det oprindelige
mål for øvrige var ikke opfyldt før supplering. Første fase er bevaret med
hashforankring i SUPPLEMENT_PLAN.json og vises pr. mutant i slutrapporten.
Der er ikke skjult nogen overlevende eller justeret på tolerance/forventninger.

Alle 25 bestilte Claude-tests består mod den uændrede evaluator. De køres
mod hver kandidat i en ny temp-kopi med importsubstitution for både v11- og
v111-navnet, også ved factory-testens import. Alle kandidater kompilerer og
giver et normalt OK-output på den samme sanity-fixture; ingen mutant er en
syntaksfejl eller en altid-crash.

Slutrapporten indeholder 28 konkrete stille vidner: CLI-exit 0, fixture-status
OK og uændrede statusfelter for samtlige hypoteser, men ændrede resultater.
Eksempler er M09 funding-fortegn, M10 cost på position, M11 bps-enhed,
M13 cost-total, M17 funding-missing-tæller og M35 ledger-hash.

## To trivielle detektionskilder er skilt ud

Checksum-testen registrerer alle 45 byteændrede kandidater, inklusive de to
ækvivalente. Den er en reel integritetsdetektor, men indgår ikke i de ovenstående
semantiske scores. Ellers ville resultatet automatisk være 100 % uden et eneste
kontrolpunkt for beregningen. Den oprindelige test og lock ændres ikke.

Tilsvarende får en mutant ikke et fund alene ved at arve den ene kendte
baseline-afvigelse mellem de to uafhængige evaluatorer. Rapporten bevarer både
rå baseline-afvigelser, checksum-fund og de konkrete nye fund pr. kandidat.
Det bogstavelige test-eller-reference-kriterium er også gemt som
`specified_criterion_detected_by`: det finder 45/45, også de ækvivalente,
på grund af checksum og den kendte baseline-forskel. Det stærkere
`semantic_detected_by` adskiller reel fejldetektion fra disse automatiske fund.
Kolonnen `detected_by` bruger tests/fixtures/begge/ingen efter disse strengere
regler. `tests` omfatter efter supplering også den eksplicit navngivne nye
afbrydelsestest; dens fund ligger separat i `added_test_failures`.

## Uafhængig reference og baseline

Egen `r3/ref_eval.py` blev opgraderet ud fra v1.1.1/v1.1/v1-specifikationerne,
før nogen Claude-kode eller tests blev åbnet. Syv spec-afledte tests bestod,
og referencekode/generator/tests blev hashet i REFERENCE_PROVENANCE.json.
De første 76 forventninger blev skrevet og hashet før kodeinspektion.

Der er nu 79 nye forventede outputs: 6 R1, 47 R2 og 26 nye R3-inputs.
Gamle R1- og R2-forventninger er ikke omskrevet. Alle nye outputs er kanonisk
JSON uden newline. De initiale og tilføjede forventninger kontrolleres mod
hver deres SHA-256-manifest før hver kørsel. Den numeriske tolerance er
uændret: `abs(a-b) <= 1e-9*max(1,abs(a),abs(b))`. Andre felter er eksakte.

De to v1.1.1-implementeringer matcher på 78/79 fixtures. Den eneste afvigelse
er R3_13_numeric_ledger: begge giver NUMERIC_ERROR, NUMERIC_OVERFLOW og ingen
delresultater, men reference bruger fejlstien `""`, mens Claude bruger
`"OverflowError"`. Specifikationen angiver ikke undtagelsesstiens konkrete
format. Det er en eksakt feltafvigelse, så der påstås ikke fuld overensstemmelse.
Hverken reference eller forventning er tilpasset efter Claude-inspektionen.

## Først overlevet, derefter fanget

| Mutant | Første blinde punkt | Særskilt tilføjelse | Slutmekanisme |
| --- | --- | --- | --- |
| M23 | Alle eksisterende p-værdier lå på samme side, selv med forkert m | R3_A01_holm_duplicate_denominator | fixtures |
| M27 | Ingen eksisterende case skelnede mellem alpha og q ved den relevante rang | R3_A02_bh_level | fixtures |
| M41 | En fuld genkørsel lykkes også med direkte overskrivning | atomic_interruption_preserves_previous_file | ny test |
| M45 | Ingen gyldig eksisterende observation ramte præcis abs(ret)=0.5 | R3_A03_extreme_equality | fixtures |

R3_A01 bruger én testbar hypotese og en fingeraftryksdublet. Analytisk t=1.875,
p≈0.0303964: korrekt m=1 afviser ved 0.05; forkert m=2 gør ikke.
R3_A02 bruger samme t, men alpha=0.01 og q_fdr=0.05. Korrekt Holm er false,
BH true; fejlens genbrug af alpha giver forkert BH false.
R3_A03 har ret=+0.5 og -0.5: korrekt n_extreme=0; mutantens tæller er 2.

Den nye skrivetest injicerer et OSError halvvejs gennem selve skrivningen,
både for direkte open og fdopen. Den tidligere komplette outputfil skal
forblive byte-identisk. Den frosne evaluator består; M41 efterlader et afbrudt
JSON-prefix i den endelige fil. Testen kræver ikke et bestemt funktionskald;
den observerer den gamle fils indhold efter skrivefejlen. Dette er et
kontrolleret afbrydelsesforsøg, ikke et bevis for strømsvigtsholdbarhed.

## Ækvivalente og begrænsninger

- M43: for endeligt r er abs(r)>0.5 identisk med r>0.5 eller r<-0.5.
  Ret er allerede gjort endeligt før predikatet; signed zero ændrer ikke dette.
- M44: T=len(xs) er heltal; T>=30 og T>29 er identiske.

De to har hverken semantiske test- eller fixture-fund. De identificeres ikke
som fejl alene på grund af checksum-testen. Mutationsdækningen gælder de
konkrete 43 fejlidéer og disse syntetiske inputs; den er ikke et bevis for
fravær af alle andre fejl. Ingen konklusioner om alpha eller handelsresultater.

## Leverancer og reproduktion

MUTATION_PLAN.md beskriver faser, alvor og isolation. MUTATION_RESULTS.json
indeholder pr. mutant klassifikation, ækvivalens, førstefund, slutmekanisme,
testnavne, fixture-felter og stille vidner. INITIAL- og AUGMENTED-rapporterne
bevarer den fulde evidens. Genkørsler skriver replay-rapporter i
`/workspace/work/` og kræver samme detektioner; de første rapporter bevares.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s copybot/research/desk/codex/r3 -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/r3/run_mutants.py --phase both
```

11 egne reference-/harness-tests består. Den aktive evaluator, dens lock,
specifikation, originale tests, lab-kode og eksisterende forventninger er
uændrede. Kun `copybot/research/desk/codex/r3/` committes.
