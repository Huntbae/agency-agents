#!/usr/bin/env python3
"""전파관리통계 적재의 공용 정규화 로직.

CSV 경로(ingest_rrb_csv.py)와 오픈API 경로(fetch_rrb_api.py)가 같은 규칙으로
'구분' 라벨과 기간 열을 해석하도록 한 곳에 모아 둔다. 두 벌로 두면 한쪽만
고쳐져 같은 원자료가 경로에 따라 다르게 적재되는 사고가 난다.

원본 라벨이 정본이다. 매핑표에 없는 '구분'은 버리지 않고 unmappedSeries 로
넘긴다 — 조용히 삼키면 통계 항목이 사라진다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "data" / "rrb_national_stats.json"

# series id -> 원본 '구분' 문자열에서 찾을 키워드 묶음. 모든 키워드가 포함되어야 매칭된다.
# 순서가 곧 우선순위다: 좁은 규칙을 먼저, 넓은 규칙을 뒤에 둔다.
LABEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("LIC_DEEMED", ("의제",)),
    ("LIC_NEW", ("신규",)),
    ("LIC_MOM", ("전월",)),
    ("LIC_YOY", ("전년",)),
    ("INSP_STATIONS", ("검사",)),
    ("FEE_AMOUNT", ("사용료",)),
    ("MON_ILLEGAL", ("불법",)),
    ("MON_TECH_VIOL", ("기술기준",)),
    ("MON_LICENSE_VIOL", ("위반",)),          # 기술기준위반보다 뒤에 두어 우선순위를 넘기지 않는다
    ("CERT_BLDG_BROADBAND", ("초고속",)),
    ("CERT_BLDG_HOMENET", ("홈네트워크",)),
    ("CERT_ICT_OPERATOR", ("사업자", "인증")),
    ("LIC_STATIONS_TOTAL", ("무선국",)),      # 가장 넓은 규칙이므로 마지막
]

PERIOD_RE = re.compile(r"(\d{4})\s*년\s*(?:(\d{1,2})\s*월)?")

# '구분' 열로 쓰일 수 있는 머리글 이름들. API 응답은 열 순서를 보장하지 않으므로
# 이름으로 찾아야 한다.
LABEL_HEADERS = ("구분", "항목", "구 분")


def normalize_period(header: str) -> str | None:
    """'2026년5월' -> '2026-05', '2023년' -> '2023'. 기간 열이 아니면 None."""
    m = PERIOD_RE.search(header.replace(" ", ""))
    if not m:
        return None
    year, month = m.group(1), m.group(2)
    return f"{year}-{int(month):02d}" if month else year


def match_series(label: str) -> str | None:
    flat = label.replace(" ", "")
    for series_id, keywords in LABEL_RULES:
        if all(kw in flat for kw in keywords):
            return series_id
    return None


def parse_number(raw) -> float | int | None:
    """'1,234' -> 1234, '△12' / '▲12' / '-12' -> -12, 빈칸·'-' -> None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw
    text = str(raw).strip().replace(",", "").replace("△", "-").replace("▲", "-")
    if text in {"", "-", "―", "N/A", "해당없음"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def period_columns(headers: list[str]) -> dict[str, str]:
    """머리글 목록 -> {원본 머리글: 기간키}. 기간으로 읽히는 열만 담는다."""
    cols: dict[str, str] = {}
    for h in headers:
        period = normalize_period(str(h))
        if period:
            cols[h] = period
    return cols


def pick_label_header(headers: list[str]) -> str | None:
    """'구분' 열의 실제 머리글 이름을 고른다."""
    for name in LABEL_HEADERS:
        if name in headers:
            return name
    # 이름이 다르면 기간으로 읽히지 않는 첫 열을 라벨 열로 본다.
    for h in headers:
        if normalize_period(str(h)) is None:
            return h
    return None


def apply_rows(doc: dict, headers: list[str], rows: list[dict], source: dict) -> dict:
    """정규화된 행들을 rrb_national_stats 문서에 제자리 반영하고 적재 리포트를 돌려준다.

    rows 는 {원본 머리글: 값} 형태의 dict 목록이다. CSV·API 어느 쪽이든 이 형태로
    맞춰서 넘기면 같은 규칙으로 해석된다.
    """
    cols = period_columns(headers)
    if not cols:
        raise ValueError(f"기간 열을 찾지 못했다. 머리글: {headers}")
    label_key = pick_label_header(headers)
    if label_key is None:
        raise ValueError(f"'구분' 열을 찾지 못했다. 머리글: {headers}")

    by_id = {s["id"]: s for s in doc["series"]}
    for series in doc["series"]:
        series["values"] = {}
        series.pop("sourceLabel", None)

    unmapped: list[dict] = []
    used: set[str] = set()

    for row in rows:
        label = str(row.get(label_key, "")).strip()
        if not label:
            continue
        values = {}
        for header, period in cols.items():
            v = parse_number(row.get(header))
            if v is not None:
                values[period] = v
        series_id = match_series(label)
        # 같은 series 에 두 행이 매칭되면 두 번째부터는 unmapped 로 보낸다.
        if series_id and series_id not in used:
            used.add(series_id)
            by_id[series_id]["values"] = values
            by_id[series_id]["sourceLabel"] = label
        else:
            unmapped.append({"sourceLabel": label, "values": values})

    doc["periods"] = [
        {"key": p, "label": h, "granularity": "MONTH" if "-" in p else "YEAR"}
        for h, p in cols.items()
    ]
    doc["unmappedSeries"] = unmapped
    doc["ingestion"] = {
        "status": "INGESTED",
        "rowsRead": len(rows),
        "seriesMapped": len(used),
        "seriesUnmapped": len(unmapped),
        **source,
    }
    return doc["ingestion"]
