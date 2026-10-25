# Udkast: likviditetsregel for nye handler i en kørende bane (2026-10-25 kl. 22:05, IKKE aktiveret)

**Status:** udkast med tørkørsel. Ikke bygget. Reglen ændrer adfærden for kørende baner, når de går ind i en mønt
senere. Det kræver brugerens særskilte beslutning (mission 12, punkt 4).

## Forslag
1. **Hvad den rammer:** kun ordrer, der åbner eller øger en position (ikke `reduce_only`) i en bane, der allerede kører.
   Lukninger, reduktioner og rebalanceringer nedad blokeres aldrig, og intet lukkes automatisk.
2. **Måling:** samme som ændring 25. Bogen læses i samme kørsel som ordren (højst 5 s gammel). Rundturen er summen af
   benenes VWAP-afstand (køb + salg) ved ordrens faktiske mængde gennem 20 niveauer. Kapacitetskurven bruges, hvis den
   er højst 24 t gammel, og den største værdi gælder.
3. **Grænse:** 0,46 % (uændret gulv). Over grænsen springes ordren over. Mangler bogen, er den tom, krydset eller for
   tynd, springes den også over.
4. **Logning:** én `paper.skipped`-hændelse pr. bane, mønt og time med målingerne. Gentagne afvisninger samme time
   tælles i samme række, ikke én række pr. minut.

## Tørkørsel på alle tidligere baneordrer (kontrafaktisk)
- 35 ordregrupper: 25 åbninger af en mønt og 10 rene lukninger. Ingen tilkøb eller rebalanceringer opad.
- Over 0,46 %: 3 af 25, og det er netop åbningerne af EPIC, HOT og MITO, som ændring 25 nu allerede stopper ved banens
  start.
- **Yderligere effekt af levetidsreglen historisk: 0 ordrer, 0 USD.**

## Anbefaling
Byg den ikke nu. Den har ingen målt effekt på historikken, og den griber ind i kørende baner. Overvej den igen, hvis
banerne begynder at lave tilkøb, eller hvis en familiebane åbner en mønt i en bog over grænsen (det overvåges i
banernes egen dekomposition).
