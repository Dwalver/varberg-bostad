import requests

USER_AGENT = "Mozilla/5.0 (bostadsbevakning-varberg; +https://github.com)"


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
        response.encoding = response.encoding or "utf-8"
        return response.text

    def post_json(self, url, payload, headers=None):
        response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json() if response.content else None
