"""Client HTTP partajat de toți scraper-ii.

Include:
- Throttling (≥1 req/sec) — pentru a nu suprasolicita cdep.ro
- User-Agent identificabil — curtoazie + ușor de contactat
- Retry automat pe 429/5xx/timeout
- Timeout default
- **Adaptor SSL legacy** — cdep.ro rulează pe Oracle HTTP Server 12c cu cipher-uri
  SHA1 (ECDHE-RSA-AES256-SHA). Python 3.10+/OpenSSL 3.x le respinge la SECLEVEL=2.
- **truststore** — folosește Windows/macOS cert store pentru a evita eroarea
  "self-signed certificate in certificate chain" când există antivirus MITM.

Configurare via env:
    CDEP_HTTP_THROTTLE_SECONDS   float   default 1.0
    CDEP_HTTP_TIMEOUT_SECONDS    float   default 30
"""

from __future__ import annotations

import os
import ssl
import threading
import time
from typing import Any, Final

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

# Folosește OS cert store în loc de certifi — necesar pe Windows cu antivirus MITM.
truststore.inject_into_ssl()

USER_AGENT: Final = (
    "cdep-api-bot/0.1 (+https://github.com/Endimion2k/cdep-api-poc; contact via GitHub issues)"
)
TIMEOUT_SECONDS: Final = float(os.environ.get("CDEP_HTTP_TIMEOUT_SECONDS", "30"))
THROTTLE_SECONDS: Final = float(os.environ.get("CDEP_HTTP_THROTTLE_SECONDS", "1.0"))

# Thread-safe throttle: lock global + timestamp last request.
# Când sunt N workers paraleli cu throttle=1.0, rezultatul efectiv e 1 req/sec
# global (nu per-worker). Pentru rate mai mare, scade throttle-ul via env.
_throttle_lock = threading.Lock()
_last_request_at: float = 0.0


class _LegacySSLAdapter(HTTPAdapter):
    """Permite conectarea la servere TLS legacy (SHA1 cipher suites).

    Necesar pentru cdep.ro (Oracle HTTP Server 12c).
    """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> Any:
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    retry = Retry(
        total=5,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = _LegacySSLAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def get(url: str, **kwargs: Any) -> requests.Response:
    """GET cu throttle global thread-safe + timeout default."""
    global _last_request_at

    with _throttle_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < THROTTLE_SECONDS:
            time.sleep(THROTTLE_SECONDS - elapsed)
        _last_request_at = time.monotonic()

    kwargs.setdefault("timeout", TIMEOUT_SECONDS)
    return _session.get(url, **kwargs)
