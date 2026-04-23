"""Client HTTP partajat de toți scraper-ii.

Include:
- Throttling (≥1 req/sec) — pentru a nu suprasolicita cdep.ro
- User-Agent identificabil — curtoazie + ușor de contactat la probleme
- Retry automat pe 429/5xx/timeout
- Timeout default
- **Adaptor SSL legacy** — cdep.ro rulează pe Oracle HTTP Server 12c cu cipher-uri
  care folosesc SHA1 (`ECDHE-RSA-AES256-SHA`). Python 3.10+ cu OpenSSL 3.x le
  respinge la SECLEVEL=2 (default). Coborâm SECLEVEL la 1 pentru compatibilitate.

Utilizare:
    from scrapers._http import get

    response = get("https://www.cdep.ro/...")
    response.raise_for_status()
    html = response.text   # requests decodează cf. Content-Type (ISO-8859-2)
"""

from __future__ import annotations

import ssl
import time
from typing import Any, Final

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

# Folosește OS certificate store (Windows/macOS) în loc de certifi.
# Necesar dacă antivirusul/firewall-ul corporate face MITM HTTPS inspection
# și injectează propriul certificat — cert-ul respectiv e în Windows Certificate
# Manager dar NU în bundle-ul certifi. Fără acest apel, apar erori de tip
# "self-signed certificate in certificate chain".
truststore.inject_into_ssl()

USER_AGENT: Final = (
    "cdep-api-bot/0.1 (+https://github.com/Endimion2k/cdep-api-poc; "
    "contact via GitHub issues)"
)
TIMEOUT_SECONDS: Final = 30
THROTTLE_SECONDS: Final = 1.0

_last_request_at: float = 0.0


class _LegacySSLAdapter(HTTPAdapter):
    """Permite conectarea la servere TLS legacy (SHA1 cipher suites).

    Necesar pentru cdep.ro (Oracle HTTP Server 12c). NU activează protocoale
    nesigure global — doar coboară SECLEVEL la 1 pentru acest adaptor.
    """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> Any:
        ctx = create_urllib3_context()
        # Permite cipher-urile SHA1 care altfel sunt blocate de SECLEVEL=2
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        # Unele servere Oracle HTTP Server necesită și legacy renegotiation
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        # Acceptă începând cu TLS 1.0 (cdep.ro suportă până la 1.2)
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    retry = Retry(
        total=5,
        backoff_factor=2.0,  # 2, 4, 8, 16, 32 seconds
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = _LegacySSLAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def get(url: str, **kwargs: Any) -> requests.Response:
    """GET cu throttle global (≥1s între cereri) și timeout default."""
    global _last_request_at

    elapsed = time.monotonic() - _last_request_at
    if elapsed < THROTTLE_SECONDS:
        time.sleep(THROTTLE_SECONDS - elapsed)

    kwargs.setdefault("timeout", TIMEOUT_SECONDS)
    response = _session.get(url, **kwargs)
    _last_request_at = time.monotonic()
    return response
