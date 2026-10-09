from bostad.sources.momentum import _area_path, fetch_momentum


def _in_varberg(item) -> bool:
    path = _area_path(item)
    return bool(path) and path[0] == "Varberg"


def fetch(http):
    return fetch_momentum(
        http,
        source="fortinova",
        base_url="https://fortinova-fastighet.momentum.se/Prod/Fortinova/PmApi/",
        app_instance="EAP-51033",
        link_base="https://minasidor.fortinova.se/market/residential/",
        include=_in_varberg,
    )
