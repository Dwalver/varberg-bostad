# Bostadsbevakning Varberg

Söker var 15:e minut efter lediga hyreslägenheter i Varberg, Veddige, Trönninge, Derome och
Åskloster hos Varbergs Bostad, Fortinova, Derome Fastighet och Qasa, och skickar en ntfy-notis
per ny annons.

- Filter (maxhyra, minsta antal rum, orter): `config.yaml`
- Redan skickade annonser: `state/seen.json` (töm `seen` för att få alla igen)
- ntfy-ämne: GitHub-secret `NTFY_TOPIC`
- Kör manuellt: fliken Actions → "Bevaka lägenheter" → Run workflow

Lokalt:

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements.txt
    .venv/Scripts/python -m pytest
    .venv/Scripts/python -m bostad.main --dry-run
