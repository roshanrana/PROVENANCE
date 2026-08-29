"""Model identity resolution against the Hugging Face Hub.

D-12. Binding a locally computed weight hash proves only that we are internally
consistent. Binding the Hub's own commit SHA and the weight file's LFS sha256
lets a validator who does not trust us confirm identity against a root we do not
control — which is the difference between an attestation and a log line.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

HUB_API = "https://huggingface.co/api/models"
DEFAULT_WEIGHTS_FILE = "model.safetensors"


class HubUnreachable(RuntimeError):
    """The Hub could not be reached or returned an unusable response.

    Retryable, and the one sanctioned degradation in this codebase: a validator
    with no network still deserves an offline answer (HLD §8.4).
    """


@dataclass(frozen=True)
class HubIdentity:
    repo_id: str
    commit_sha: str
    weights_file: str
    weights_lfs_sha256: str


def _extract(payload: Mapping[str, Any], repo_id: str, weights_file: str) -> HubIdentity:
    commit_sha = payload.get("sha")
    if not commit_sha:
        raise HubUnreachable(f"Hub response for {repo_id} carried no commit sha")

    for sibling in payload.get("siblings") or []:
        if sibling.get("rfilename") != weights_file:
            continue
        lfs = sibling.get("lfs") or {}
        digest = lfs.get("sha256") or lfs.get("oid")
        if not digest:
            raise HubUnreachable(
                f"{repo_id}:{weights_file} has no LFS sha256 — cannot anchor identity"
            )
        return HubIdentity(repo_id, commit_sha, weights_file, digest)

    raise HubUnreachable(f"{repo_id} does not list {weights_file}")


def resolve_model_identity(
    repo_id: str,
    *,
    weights_file: str = DEFAULT_WEIGHTS_FILE,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> HubIdentity:
    """Resolve *repo_id* to its Hub commit SHA and weight-file LFS digest.

    ``PROVENANCE_HF_OFFLINE=1`` short-circuits to :class:`HubUnreachable` so an
    offline run is explicit rather than an accident of connectivity.
    """
    if os.environ.get("PROVENANCE_HF_OFFLINE") == "1":
        raise HubUnreachable("PROVENANCE_HF_OFFLINE=1")

    url = f"{HUB_API}/{repo_id}"
    params = {"blobs": "true"}
    headers = {}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.get(url, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise HubUnreachable(f"{type(exc).__name__}: {exc}") from exc
    except ValueError as exc:
        raise HubUnreachable(f"Hub returned unparseable JSON: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    return _extract(payload, repo_id, weights_file)
