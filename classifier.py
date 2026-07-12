"""Classify disclosure report names into investment-event categories."""

CATEGORIES: list[tuple[str, list[str]]] = [
    ("자본조달", ["유상증자", "무상증자", "전환사채", "신주인수권부사채", "교환사채", "CB발행", "BW발행"]),
    ("사업", ["단일판매", "공급계약", "수주", "신규시설투자", "투자결정"]),
    ("주주환원", ["자기주식", "배당", "소각", "자사주"]),
    ("지배구조/리스크", [
        "최대주주변경", "최대주주 변경", "소송", "회생", "감자", "합병", "분할", "영업정지",
        "불성실공시", "관리종목", "상장폐지", "횡령", "배임",
    ]),
]


def classify(report_nm: str) -> str | None:
    for category, keywords in CATEGORIES:
        for kw in keywords:
            if kw in report_nm:
                return category
    return None


def classify_disclosures(disclosures: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Return (classified_list, category_counts). Unclassified items are excluded."""
    classified = []
    counts: dict[str, int] = {}
    for item in disclosures:
        cat = classify(item.get("report_nm", ""))
        if cat:
            classified.append({**item, "category": cat})
            counts[cat] = counts.get(cat, 0) + 1
    return classified, counts
