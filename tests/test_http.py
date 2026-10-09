import requests

from bostad.http import decode_text


def _response(content: bytes, content_type: str) -> requests.Response:
    response = requests.Response()
    response._content = content
    response.status_code = 200
    response.headers["Content-Type"] = content_type
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    return response


def test_html_without_charset_is_decoded_as_utf8():
    response = _response("Månadsavgift Trönninge".encode("utf-8"), "text/html")
    assert decode_text(response) == "Månadsavgift Trönninge"


def test_explicit_charset_is_respected():
    response = _response("Månadsavgift".encode("iso-8859-1"), "text/html; charset=iso-8859-1")
    assert decode_text(response) == "Månadsavgift"
