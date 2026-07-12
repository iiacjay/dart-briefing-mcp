"""Download and parse DART corpCode.xml, with 24h file cache."""

import asyncio
import io
import logging
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
CACHE_FILE = Path("corp_code_cache.xml")
CACHE_TTL = 86400  # 24h

# In-memory index: list of dicts
_corp_list: list[dict] = []
_loaded_at: float = 0.0
_lock = asyncio.Lock()


def _is_cache_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    return (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_TTL


def _parse_xml(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    corps = []
    for item in root.iter("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        corp_name = (item.findtext("corp_name") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        modify_date = (item.findtext("modify_date") or "").strip()
        corps.append(
            {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "listed": bool(stock_code and stock_code.strip()),
                "modify_date": modify_date,
            }
        )
    return corps


async def _download_and_parse() -> list[dict]:
    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(CORP_CODE_URL, params={"crtfc_key": api_key})
        r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        xml_filename = next(n for n in zf.namelist() if n.endswith(".xml"))
        xml_bytes = zf.read(xml_filename)

    CACHE_FILE.write_bytes(xml_bytes)
    logger.info("corpCode downloaded: %d bytes", len(xml_bytes))
    return _parse_xml(xml_bytes)


async def ensure_loaded() -> None:
    global _corp_list, _loaded_at
    async with _lock:
        if _corp_list and (time.time() - _loaded_at) < CACHE_TTL:
            return
        if _is_cache_fresh():
            xml_bytes = CACHE_FILE.read_bytes()
            _corp_list = _parse_xml(xml_bytes)
            logger.info("corpCode loaded from file cache: %d corps", len(_corp_list))
        else:
            _corp_list = await _download_and_parse()
            logger.info("corpCode downloaded fresh: %d corps", len(_corp_list))
        _loaded_at = time.time()


def search(query: str, max_results: int = 10) -> list[dict]:
    """Search by corp_name (partial) or stock_code (exact 6-digit)."""
    query = query.strip()
    if not query:
        return []

    results = []
    # Exact stock_code match first
    if query.isdigit() and len(query) == 6:
        for c in _corp_list:
            if c["stock_code"] == query:
                results.append(c)
        if results:
            return results[:max_results]

    # Partial name match — listed first
    matches = [c for c in _corp_list if query in c["corp_name"]]
    matches.sort(key=lambda c: (not c["listed"], c["corp_name"]))
    return matches[:max_results]


def get_by_corp_code(corp_code: str) -> dict | None:
    for c in _corp_list:
        if c["corp_code"] == corp_code:
            return c
    return None
