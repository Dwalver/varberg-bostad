from bostad.sources.momentum import fetch_momentum


def fetch(http):
    return fetch_momentum(
        http,
        source="varbergsbostad",
        base_url="https://varberg-fastighet.momentum.se/Prod/Varberg/PmApi/",
        app_instance="EAP-13681",
        link_base="https://minasidor.varbergsbostad.se/market/residential/",
    )
