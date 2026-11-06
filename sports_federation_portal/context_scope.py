"""Small, pure context validation shared by routes and return navigation."""

from urllib.parse import urlencode, urlsplit, parse_qsl


def positive_id(value):
    if value in (None, ""):
        return None
    if (
        isinstance(value, bool)
        or len(str(value)) > 10
        or not str(value).isascii()
        or not str(value).isdigit()
        or int(value) <= 0
        or int(value) > 2147483647
    ):
        raise ValueError("Invalid context identifier")
    return int(value)


def scoped_url(path, club=None, team=None, registration=None):
    parts = urlsplit(path)
    if (
        parts.scheme
        or parts.netloc
        or parts.fragment
        or not parts.path.startswith("/my/")
    ):
        raise ValueError("Invalid context destination")
    values = dict(parse_qsl(parts.query))
    for key, value in (("club", club), ("team", team), ("registration", registration)):
        value = positive_id(value)
        if value:
            values[key] = str(value)
    return parts.path + ("?" + urlencode(values) if values else "")
