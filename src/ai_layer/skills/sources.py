from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request

from ai_layer import __version__
from ai_layer.skills.constants import DEFAULT_SKILL_CATALOG, MAX_ARCHIVE_BYTES
from ai_layer.skills.contracts import _slugify


def _validate_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only explicit https:// skill URLs are accepted")
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Refusing local/private skill URL")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve skill URL host: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"Refusing local/private skill URL address: {ip}")
    return parsed


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(url: str, *, max_bytes: int = MAX_ARCHIVE_BYTES) -> bytes:
    _validate_url(url)
    opener = urllib.request.build_opener(_SafeRedirect())
    request = urllib.request.Request(
        url, headers={"User-Agent": f"ai-layer-skill-import/{__version__}"}
    )
    with opener.open(request, timeout=10) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("Remote skill source is too large")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Remote skill source is too large")
    return data


def _normalize_remote_skill_url(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    if parsed.hostname and parsed.hostname.casefold() == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and not parsed.query and not parsed.fragment:
            return f"https://github.com/{parts[0]}/{parts[1]}/archive/refs/heads/main.zip"
    return source


def default_skill_catalog() -> list[dict]:
    """Return trusted catalog metadata, never remote skill bodies."""
    return [{"slug": slug, **spec} for slug, spec in sorted(DEFAULT_SKILL_CATALOG.items())]


def _catalog_source(source: str) -> tuple[str, dict[str, str]] | None:
    if not source.casefold().startswith("catalog:"):
        return None
    slug = _slugify(source.split(":", 1)[1])
    spec = DEFAULT_SKILL_CATALOG.get(slug)
    if spec is None:
        raise ValueError(f"Unknown default skill catalog entry: {slug}")
    return slug, dict(spec)
