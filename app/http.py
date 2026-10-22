import logging
import os
from typing import Literal

import httpx
from fastapi import HTTPException, Response

logger = logging.getLogger(__name__)


def forward(
    service: Literal["fleet", "agreement"],
    method: str,
    path: str,
    authorization: str,
    body: dict[str, object] | None = None,
) -> Response:
    defaults = {"fleet": "http://127.0.0.1:8001", "agreement": "http://127.0.0.1:8002"}
    base_url = os.environ.get(f"{service.upper()}_SERVICE_URL", defaults[service])
    try:
        upstream = httpx.request(
            method,
            base_url.rstrip("/") + path,
            headers={"Authorization": authorization},
            json=body,
            timeout=10,
            trust_env=False,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        logger.warning("%s service timed out", service)
        raise HTTPException(
            status_code=504, detail=f"{service} service timed out"
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("%s service unavailable", service)
        raise HTTPException(
            status_code=502, detail=f"{service} service unavailable"
        ) from exc
    headers = {
        name: upstream.headers[name]
        for name in ("content-type", "www-authenticate")
        if name in upstream.headers
    }
    return Response(
        content=upstream.content, status_code=upstream.status_code, headers=headers
    )
