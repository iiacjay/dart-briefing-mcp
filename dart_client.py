"""DART OpenAPI wrapper with caching and error handling."""

import asyncio
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DART_BASE = "https://opendart.fss.or.kr/api"

DART_STATUS_MESSAGES = {
    "000": "정상",
    "010": "등록되지 않은 키",
    "011": "사용할 수 없는 키 (접근 IP 제한)",
    "013": "조회된 데이터가 없습니다",
    "020": "요청 제한을 초과했습니다 (일일 한도 초과)",
    "100": "필드 누락 또는 잘못된 요청",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
    "901": "사용자 계정 정지",
}

# Simple in-memory cache: {cache_key: (timestamp, data)}
_cache: dict[str, tuple[float, Any]] = {}

DISCLOSURE_TYPE_MAP = {
    "정기공시": "A",
    "주요사항보고": "B",
    "발행공시": "C",
    "지분공시": "D",
    "기타": "E",
    "거래소공시": "I",
    "전체": None,
}

DISCLAIMER = "본 정보는 투자 판단 참고용이며 투자 권유가 아닙니다. 출처: 금융감독원 DART"


def _get_api_key() -> str:
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다.")
    return key


def _cache_get(key: str, ttl: int) -> Any | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


def _viewer_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


async def _get(endpoint: str, params: dict, cache_ttl: int = 0) -> dict:
    params = {k: v for k, v in params.items() if v is not None}
    cache_key = endpoint + str(sorted(params.items()))
    if cache_ttl:
        cached = _cache_get(cache_key, cache_ttl)
        if cached is not None:
            logger.debug("cache hit: %s", cache_key[:80])
            return cached

    params["crtfc_key"] = _get_api_key()
    url = f"{DART_BASE}/{endpoint}"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(2):
                try:
                    r = await client.get(url, params=params)
                    r.raise_for_status()
                    break
                except (httpx.TimeoutException, httpx.ConnectError):
                    if attempt == 1:
                        raise
                    await asyncio.sleep(1)
    finally:
        elapsed = time.time() - start
        safe_params = {k: v for k, v in params.items() if k != "crtfc_key"}
        logger.info("%s %s %.2fs", endpoint, safe_params, elapsed)

    data = r.json()
    status = data.get("status", "")
    if status not in ("000", "013"):
        msg = DART_STATUS_MESSAGES.get(status, f"알 수 없는 오류 (status={status})")
        raise RuntimeError(f"DART API 오류: {msg}")

    if cache_ttl:
        _cache_set(cache_key, data)
    return data


async def fetch_disclosures(
    corp_code: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None = None,
    page_count: int = 40,
) -> list[dict]:
    params = {
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": page_count,
    }
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty

    data = await _get("list.json", params, cache_ttl=600)
    if data.get("status") == "013":
        return []

    items = data.get("list", [])
    result = []
    for item in items:
        rcept_no = item.get("rcept_no", "")
        result.append(
            {
                "report_nm": item.get("report_nm", ""),
                "rcept_dt": item.get("rcept_dt", ""),
                "flr_nm": item.get("flr_nm", ""),
                "rcept_no": rcept_no,
                "viewer_url": _viewer_url(rcept_no),
            }
        )
    return result


async def fetch_company_profile(corp_code: str) -> dict:
    data = await _get("company.json", {"corp_code": corp_code}, cache_ttl=3600)
    return data
