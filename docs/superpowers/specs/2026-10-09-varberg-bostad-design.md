# Bostadsbevakning Varberg – design

Datum: 2026-10-09

## Syfte

Automatiskt hitta lediga hyreslägenheter i Varbergsområdet och skicka en pushnotis (ntfy) per
annons. Första körningen skickar alla annonser som matchar just nu; därefter bara nya.

## Krav

- **Orter:** Varberg (staden inkl. stadsdelar), Veddige, Trönninge, Derome, Åskloster.
  Övriga orter i kommunen (t.ex. Tvååker, Bua, Träslövsläge) filtreras bort.
- **Hyra:** högst 11 000 kr/mån.
- **Rum:** minst 3.
- **Kontrakt:** endast förstahand, ingen korttidsuthyrning.
- **Källor:** Varbergs Bostad, Fortinova, Derome Fastighet, Qasa (Blocket Bostad ingår i Qasa).
- **Notiser:** ntfy, en notis per annons, med länk till annonsen.
- **Drift:** GitHub Actions i ett publikt repo, var 15:e minut.

## Källor (verifierat 2026-10-09)

| Källa | Metod | Detaljer |
|---|---|---|
| Varbergs Bostad | Momentum JSON | `GET https://varberg-fastighet.momentum.se/Prod/Varberg/PmApi/v2/market/objects`, headers `X-Api-Key` + `X-Momentum-Api-App-Instance: EAP-13681`, `Accept: application/json`. Publik klientnyckel från `minasidor.varbergsbostad.se/assets/app-settings.json`. Svar `{count, items[]}`; filtrera `queueType == "residential"`. Ort i `location.areaPath[0].displayName` (stadsdel). Länk: `https://minasidor.varbergsbostad.se/market/residential/{id}`. |
| Fortinova | Momentum JSON | Samma API: `https://fortinova-fastighet.momentum.se/Prod/Fortinova/PmApi/`, app-instans `EAP-51033`. Omfattar flera kommuner; `areaPath[0]` är kommun – behåll bara `Varberg`; `areaPath[1]` är ort (t.ex. `Tvååker`, `Centrala Varberg`, `Väröbacka`) och används som `area`. Länk: `https://minasidor.fortinova.se/market/residential/{id}`. |
| Derome Fastighet | HTML | `https://www.deromefastighet.se/lediga-lagenheter` listar annonser server-renderat med länkar `/lediga-lagenheter/lagenhet/{id}`. Detaljsidan ger adress, ort, rum, kvm, hyra, inflyttning, sista ansökan. |
| Qasa | GraphQL | `POST https://api.qasa.se/graphql`, `homeIndexSearch(params:{areaIdentifier:["se/varberg"]})`. Fält: `id rent tenantBaseFee roomCount squareMeters firstHand startDate endDate shared homeType publishedAt location{locality}`. Länk: `https://qasa.se/sv/home/{id}` (qasa.se blockerar curl med 429; länken verifieras i webbläsare vid implementation). |

Momentum-nyckeln är paginerad (`count` > antal `items`); källmodulen ska hämta alla sidor.
Exakt pagineringsparameter fastställs vid implementation mot API:t.

## Arkitektur

```
varberg-bostad/
  bostad/
    model.py            Listing (dataclass)
    sources/
      momentum.py       gemensam Momentum-klient (används av två källor)
      varbergs_bostad.py
      fortinova.py
      derome.py
      qasa.py
    filters.py          ort-, hyres-, rum- och kontraktsfilter
    notify.py           ntfy
    state.py            läs/skriv seen.json + felräknare
    main.py             orkestrering, --dry-run
  config.yaml           orter, stadsdelar, uteslutna orter, maxhyra, minrum
  state/seen.json
  tests/ + tests/fixtures/   sparade riktiga svar per källa
  .github/workflows/check.yml
```

Varje källa är en funktion `fetch() -> list[Listing]` utan andra beroenden än HTTP. Filter,
notis och tillstånd känner inte till källorna.

### Listing

`source, id, url, address, area (ort/stadsdel som källan anger), rooms (float|None),
size_sqm, rent (kr/mån, inkl. ev. Qasa-avgift), available_from, apply_by, first_hand (bool),
end_date`. Unik nyckel: `f"{source}:{id}"`.

## Flöde per körning

1. Hämta från alla källor; en källa som kastar fel loggas och hoppas över.
2. Filtrera:
   - **Ort:** normalisera (gemener, trimma). Godkänd om den finns i `allowed_areas`
     (orterna + Varbergs stadsdelar). Avvisad om den finns i `excluded_areas`.
     Annars skickas den med markeringen "⚠️ okänt område" – hellre en extra notis än en missad.
   - **Hyra** ≤ `max_rent`; **rum** ≥ `min_rooms`. Saknat värde → skickas (med frågetecken i notisen).
   - **Kontrakt:** Varbergs Bostad/Fortinova/Derome räknas alltid som förstahand utan slutdatum.
     Qasa kräver `firstHand == true` och `endDate == null`.
3. Ta bort annonser vars nyckel redan finns i `seen.json`.
4. Skicka en ntfy-notis per ny annons; lägg till nyckeln i `seen.json` först när sändningen lyckats.
5. Spara `seen.json`; workflowen committar filen om den ändrats.

## Notis

- Server: `https://ntfy.sh` (konfigurerbar), ämne från secret `NTFY_TOPIC`.
- Titel: `3 rok, 72 m² – Trönninge`
- Text: `10 618 kr/mån · inflytt 2027-01-01 · sök senast 2026-10-20 · Derome`
- `Click`-header = annonslänk. Taggar: `house`.

## Felhantering

- Fel i en källa påverkar inte de andra.
- `seen.json` innehåller även `failures: {source: antal_fel_i_rad}`. Vid 3 fel i rad skickas
  en varningsnotis ("Källa X har slutat fungera") en gång; räknaren nollställs vid lyckad hämtning.
- En källa som plötsligt returnerar 0 annonser räknas inte som fel (kan vara tomt på riktigt).

## Drift

- Publikt GitHub-repo, workflow `schedule: cron "*/15 * * * *"` + `workflow_dispatch`.
- Workflow-steg: checkout → Python 3.12 → `pip install -r requirements.txt` →
  `python -m bostad.main` → commit `state/seen.json` vid ändring (`contents: write`).
- GitHub stänger av schemalagda workflows efter 60 dagar utan aktivitet i repot; workflowen
  committar en `state/heartbeat.txt` om senaste commit är äldre än 30 dagar.
- Beroenden: `requests`, `beautifulsoup4`, `pyyaml`, `pytest`.

## Test

- Fixtures: sparade svar från varje källa (2026-10-09). Tester för tolkning per källa,
  för varje filterregel och för ny/sedd-logik.
- `python -m bostad.main --dry-run` skriver ut notiserna utan att skicka eller spara.

## Utanför omfattning

- Webbsida/översikt, e-post, automatisk ansökan, fler källor (kan läggas till som nya moduler).
