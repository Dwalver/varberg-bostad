import requests

USER_AGENT = "Mozilla/5.0 (bostadsbevakning-varberg; +https://github.com)"


def decode_text(response) -> str:
    """Decode a response; requests assumes ISO-8859-1 for text/* without charset, so use UTF-8 then."""
    if "charset" not in response.headers.get("Content-Type", "").lower():
        return response.content.decode("utf-8", errors="replace")
    return response.text


class Http:
    def __init__(self, timeout: float = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get_json(self, url, headers=None):
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_text(self, url, headers=None):
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return decode_text(response)

    def post_json(self, url, payload, headers=None):
        response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json() if response.content else None
