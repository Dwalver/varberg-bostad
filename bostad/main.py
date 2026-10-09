import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from bostad import notify
from bostad.filters import filter_listings, load_config
from bostad.http import Http
from bostad.sources import derome, fortinova, qasa, varbergs_bostad
from bostad.state import load_state, save_state

ALERT_AFTER = 3
CONFIG_PATH = "config.yaml"
STATE_PATH = "state/seen.json"
SOURCES = {
    "varbergsbostad": varbergs_bostad.fetch,
    "fortinova": fortinova.fetch,
    "derome": derome.fetch,
    "qasa": qasa.fetch,
}
log = logging.getLogger("bostad")


def run(http, criteria, state, sender, sources, now) -> int:
    listings = []
    for name, fetch in sources.items():
        try:
            found = fetch(http)
        except Exception as error:
            count = state.failures.get(name, 0) + 1
            state.failures[name] = count
            log.error("%s misslyckades (%d i rad): %s", name, count, error)
            if count == ALERT_AFTER:
                try:
                    sender(notify.format_alert(name, str(error)))
                except Exception as send_error:
                    log.error("Kunde inte skicka varning: %s", send_error)
            continue
        state.failures[name] = 0
        log.info("%s: %d annonser", name, len(found))
        listings.extend(found)

    sent = 0
    for match in filter_listings(listings, criteria):
        key = match.listing.key
        if key in state.seen:
            continue
        try:
            sender(notify.format_message(match))
        except Exception as error:
            log.error("Kunde inte skicka %s: %s", key, error)
            continue
        state.seen[key] = now
        sent += 1
    return sent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bevaka lediga lägenheter i Varbergsområdet")
    parser.add_argument("--dry-run", action="store_true", help="skriv ut notiser i stället för att skicka")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    criteria, server = load_config(CONFIG_PATH)
    state = load_state(STATE_PATH)
    http = Http()

    if args.dry_run:
        def sender(payload):
            print(json.dumps(payload, ensure_ascii=False))
    else:
        topic = os.environ.get("NTFY_TOPIC")
        if not topic:
            log.error("NTFY_TOPIC saknas")
            return 2

        def sender(payload):
            notify.send(http, server, topic, payload)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sent = run(http, criteria, state, sender, SOURCES, now)
    log.info("Skickade %d nya annonser", sent)
    if not args.dry_run:
        save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
