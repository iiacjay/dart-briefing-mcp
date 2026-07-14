"""DART 공시 브리핑 MCP 서버."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolAnnotations

import corp_code as cc
import dart_client as dc
from classifier import classify_disclosures

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


@asynccontextmanager
async def lifespan(app):
    await cc.ensure_loaded()
    logger.info("corpCode index ready")
    yield


mcp = FastMCP(
    "dart-briefing-mcp",
    instructions=(
        "관심 기업의 DART 전자공시를 검색·필터링해 투자자 관점 브리핑 재료를 제공합니다. "
        "모든 결과에 DART 원문 링크가 포함됩니다."
    ),
    lifespan=lifespan,
)


def _date_range(days: int) -> tuple[str, str]:
    end = date.today()
    bgn = end - timedelta(days=max(1, min(days, 90)))
    return bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d")


async def _resolve_corp(company: str) -> dict | str:
    """Return corp dict on unique match, or error string."""
    await cc.ensure_loaded()
    company = company.strip()

    # 8자리 숫자 → corp_code 직접 조회
    if company.isdigit() and len(company) == 8:
        hit = cc.get_by_corp_code(company)
        if hit:
            return hit

    hits = cc.search(company)
    if not hits:
        return f"'{company}'에 해당하는 기업을 찾을 수 없습니다."
    if len(hits) == 1:
        return hits[0]
    # Exact name match
    exact = [h for h in hits if h["corp_name"] == company]
    if len(exact) == 1:
        return exact[0]
    names = [f"{h['corp_name']}({h['stock_code'] or h['corp_code']})" for h in hits[:5]]
    return f"여러 기업이 검색됩니다. 종목코드나 정확한 기업명을 사용해주세요: {', '.join(names)}"


@mcp.tool(
    description=(
        "[공시 브리핑] 기업명(일부) 또는 종목코드 6자리로 DART 기업 고유번호를 조회합니다. "
        "동명 다수일 때 후보 목록을 반환하므로 에이전트가 재질문할 수 있습니다."
    ),
    annotations=_READ_ONLY,
)
async def search_company(query: str) -> dict:
    """기업명 또는 종목코드로 DART 등록 기업을 검색합니다."""
    if len(query.strip()) < 2:
        return {"error": "검색어는 최소 2자 이상이어야 합니다.", "disclaimer": dc.DISCLAIMER}

    await cc.ensure_loaded()
    hits = cc.search(query.strip())
    if not hits:
        return {"error": f"'{query}'에 해당하는 기업을 찾을 수 없습니다.", "disclaimer": dc.DISCLAIMER}

    return {
        "results": [
            {
                "corp_name": h["corp_name"],
                "corp_code": h["corp_code"],
                "stock_code": h["stock_code"],
                "listed": h["listed"],
            }
            for h in hits
        ],
        "total": len(hits),
        "disclaimer": dc.DISCLAIMER,
    }


@mcp.tool(
    description=(
        "[공시 브리핑] 기업의 최근 DART 공시 목록을 조회합니다. "
        "company 파라미터에는 기업명(예: '삼성전자') 또는 종목코드 6자리(예: '005930')를 입력하세요. "
        "corp_code(8자리 숫자)도 허용됩니다. "
        "disclosure_type: '정기공시' | '주요사항보고' | '발행공시' | '지분공시' | '전체'. "
        "각 공시에 DART 원문 링크(viewer_url)가 포함됩니다."
    ),
    annotations=_READ_ONLY,
)
async def get_recent_disclosures(
    company: str,
    days: int = 7,
    disclosure_type: str = "전체",
) -> dict:
    """기업의 최근 공시 목록을 반환합니다."""
    corp = await _resolve_corp(company)
    if isinstance(corp, str):
        return {"error": corp, "disclaimer": dc.DISCLAIMER}

    bgn_de, end_de = _date_range(days)
    pblntf_ty = dc.DISCLOSURE_TYPE_MAP.get(disclosure_type)

    try:
        items = await dc.fetch_disclosures(
            corp_code=corp["corp_code"],
            bgn_de=bgn_de,
            end_de=end_de,
            pblntf_ty=pblntf_ty,
        )
    except RuntimeError as e:
        return {"error": str(e), "disclaimer": dc.DISCLAIMER}

    return {
        "company": corp["corp_name"],
        "corp_code": corp["corp_code"],
        "stock_code": corp["stock_code"],
        "period": f"{bgn_de}~{end_de}",
        "disclosure_type": disclosure_type,
        "count": len(items),
        "disclosures": items,
        "disclaimer": dc.DISCLAIMER,
    }


@mcp.tool(
    description=(
        "[공시 브리핑] 주가 민감 주요 공시(유상증자·수주·자사주·최대주주변경 등)를 카테고리별로 분류해 반환합니다. "
        "company 파라미터에는 기업명(예: '삼성전자') 또는 종목코드 6자리(예: '005930')를 입력하세요. "
        "corp_code(8자리 숫자)도 허용됩니다. "
        "에이전트가 '이번 달 자본조달 2건, 수주 1건' 식 브리핑을 만들기 좋습니다."
    ),
    annotations=_READ_ONLY,
)
async def get_major_events(company: str, days: int = 30) -> dict:
    """주가 민감 주요 공시를 분류해 반환합니다."""
    corp = await _resolve_corp(company)
    if isinstance(corp, str):
        return {"error": corp, "disclaimer": dc.DISCLAIMER}

    bgn_de, end_de = _date_range(days)

    try:
        items_b = await dc.fetch_disclosures(corp["corp_code"], bgn_de, end_de, pblntf_ty="B")
        items_i = await dc.fetch_disclosures(corp["corp_code"], bgn_de, end_de, pblntf_ty="I")
    except RuntimeError as e:
        return {"error": str(e), "disclaimer": dc.DISCLAIMER}

    all_items = items_b + items_i
    classified, counts = classify_disclosures(all_items)

    return {
        "company": corp["corp_name"],
        "corp_code": corp["corp_code"],
        "stock_code": corp["stock_code"],
        "period": f"{bgn_de}~{end_de}",
        "category_summary": counts,
        "total_major_events": len(classified),
        "events": classified,
        "disclaimer": dc.DISCLAIMER,
    }


@mcp.tool(
    description=(
        "[공시 브리핑] 기업 개황(대표자, 업종, 설립일, 상장시장, 홈페이지)을 반환합니다. "
        "company 파라미터에는 기업명(예: '삼성전자') 또는 종목코드 6자리(예: '005930')를 입력하세요. "
        "corp_code(8자리 숫자)도 허용됩니다."
    ),
    annotations=_READ_ONLY,
)
async def get_company_profile(company: str) -> dict:
    """기업 기본 정보를 반환합니다."""
    corp = await _resolve_corp(company)
    if isinstance(corp, str):
        return {"error": corp, "disclaimer": dc.DISCLAIMER}

    try:
        data = await dc.fetch_company_profile(corp["corp_code"])
    except RuntimeError as e:
        return {"error": str(e), "disclaimer": dc.DISCLAIMER}

    corp_cls_map = {"Y": "유가증권시장(KOSPI)", "K": "코스닥(KOSDAQ)", "N": "코넥스", "E": "기타"}
    corp_cls = data.get("corp_cls", "")
    return {
        "corp_name": data.get("corp_name", ""),
        "ceo_nm": data.get("ceo_nm", ""),
        "induty_code": data.get("induty_code", ""),
        "est_dt": data.get("est_dt", ""),
        "stock_market": corp_cls_map.get(corp_cls, corp_cls),
        "stock_code": data.get("stock_code", ""),
        "hm_url": data.get("hm_url", ""),
        "adres": data.get("adres", ""),
        "phn_no": data.get("phn_no", ""),
        "disclaimer": dc.DISCLAIMER,
    }


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok", "server": "dart-briefing-mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
