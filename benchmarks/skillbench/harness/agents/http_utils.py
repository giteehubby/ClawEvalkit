from __future__ import annotations

import os
import pathlib
import ssl


def _env_cafile() -> str | None:
    for key in ("SKILLBENCH_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        value = os.environ.get(key)
        if not value:
            continue
        path = pathlib.Path(value)
        if path.exists():
            return str(path)
    return None


def _env_capath() -> str | None:
    value = os.environ.get("SSL_CERT_DIR")
    if not value:
        return None
    path = pathlib.Path(value)
    if path.exists():
        return str(path)
    return None


def build_ssl_context() -> ssl.SSLContext:
    cafile = _env_cafile()
    capath = _env_capath()
    if cafile or capath:
        return ssl.create_default_context(cafile=cafile, capath=capath)

    try:
        import certifi  # type: ignore
    except Exception:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())
