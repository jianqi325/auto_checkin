from __future__ import annotations

from typing import Any

from .fishc import FishCSite

SITE_REGISTRY = {
    "fishc": FishCSite,
}


def create_site(site: str, **kwargs: Any):
    if site not in SITE_REGISTRY:
        raise KeyError(f"Unsupported site: {site}")
    return SITE_REGISTRY[site](**kwargs)
