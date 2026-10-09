class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _lookup(self, url, payload=None):
        self.calls.append(url)
        if url not in self.routes:
            raise RuntimeError("404 " + url)
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        return value(payload) if callable(value) else value

    def get_json(self, url, headers=None):
        return self._lookup(url)

    def get_text(self, url, headers=None):
        return self._lookup(url)

    def post_json(self, url, payload, headers=None):
        return self._lookup(url, payload)
