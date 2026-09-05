#!/usr/bin/env python3
"""중앙전파관리소 전파관리통계 CSV -> data/rrb_national_stats.json 정규화 적재기.

원본(공공데이터포털 15054180)은 가로형 표다. 1열이 '구분', 나머지 열이
'2023년', '2024년', '2025년', '2026년1월' … 같은 기간 열이다. 이 스크립트는

  1) 기간 열 머리글을 'YYYY' / 'YYYY-MM' 키로 정규화하고,
  2) '구분' 문자열을 rrb_national_stats.json 의 series id 로 매핑하며,
  3) 매핑되지 않은 행은 버리지 않고 unmapped 로 남겨 원본 라벨을 보존한다.

원본 라벨이 정본이다. 매핑표에 없는 '구분'이 나오면 그 행을 unmappedSeries 에
원문 그대로 실어 두고 경고를 낸다 — 조용히 삼키면 통계 항목이 사라진다.

사용법:
    python3 scripts/ingest_rrb_csv.py 전파관리통계_20260531.csv
    python3 scripts/ingest_rrb_csv.py 전파관리통계.csv --out data/rrb_national_stats.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "data" / "rrb_national_stats.json"
ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8")

# series id -> 원본 '구분' 문자열에서 찾을 키워드 묶음. 모든 키워드가 포함되어야 매칭된다.
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


def read_rows(path: Path) -> list[list[str]]:
    """인코딩을 순서대로 시도하며 CSV를 읽는다."""
    last_error: Exception | None = None
    for enc in ENCODINGS:
        try:
            with path.open(encoding=enc, newline="") as fh:
                return [row for row in csv.reader(fh) if any(c.strip() for c in row)]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise SystemExit(f"CSV 디코딩 실패({path}): 시도한 인코딩 {ENCODINGS} / {last_error}")


def normalize_period(header: str) -> str | None:
    """'2026년5월' -> '2026-05', '2023년' -> '2023'."""
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


def parse_number(raw: str) -> float | int | None:
    """'1,234' -> 1234, '△12' / '-12' -> -12, 빈칸·'-' -> None."""
    text = raw.strip().replace(",", "").replace("△", "-").replace("▲", "-")
    if text in {"", "-", "―", "N/A", "해당없음"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def ingest(csv_path: Path, target: Path) -> dict:
    rows = read_rows(csv_path)
    if not rows:
        raise SystemExit(f"빈 CSV: {csv_path}")

    header, *body = rows
    period_cols: dict[int, str] = {}
    for idx, cell in enumerate(header[1:], start=1):
        period = normalize_period(cell)
        if period:
            period_cols[idx] = period
    if not period_cols:
        raise SystemExit(f"기간 열을 찾지 못했다. 머리글: {header}")

    doc = json.loads(target.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in doc["series"]}
    for series in doc["series"]:
        series["values"] = {}
        series.pop("sourceLabel", None)

    unmapped: list[dict] = []
    used: set[str] = set()

    for row in body:
        label = row[0].strip()
        if not label:
            continue
        values = {
            period: parse_number(row[idx])
            for idx, period in period_cols.items()
            if idx < len(row) and parse_number(row[idx]) is not None
        }
        series_id = match_series(label)
        # 같은 series 에 두 행이 매칭되면 두 번째부터는 unmapped 로 보낸다.
        if series_id and series_id not in used:
            used.add(series_id)
            by_id[series_id]["values"] = values
            by_id[series_id]["sourceLabel"] = label
        else:
            unmapped.append({"sourceLabel": label, "values": values})

    doc["periods"] = [
        {
            "key": p,
            "label": next(h for i, h in enumerate(header) if i in period_cols and period_cols[i] == p),
            "granularity": "MONTH" if "-" in p else "YEAR",
        }
        for p in dict.fromkeys(period_cols.values())
    ]
    doc["unmappedSeries"] = unmapped
    doc["ingestion"] = {
        "status": "INGESTED",
        "sourceFile": csv_path.name,
        "rowsRead": len(body),
        "seriesMapped": len(used),
        "seriesUnmapped": len(unmapped),
        "tool": "scripts/ingest_rrb_csv.py",
    }
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc["ingestion"]


def main() -> int:
    ap = argparse.ArgumentParser(description="전파관리통계 CSV 정규화 적재")
    ap.add_argument("csv", type=Path, help="공공데이터포털에서 내려받은 CSV 경로")
    ap.add_argument("--out", type=Path, default=DEFAULT_TARGET, help="적재 대상 JSON")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV를 찾을 수 없다: {args.csv}")
    if not args.out.exists():
        raise SystemExit(
            f"적재 대상 JSON이 없다: {args.out}\n"
            "이 스크립트는 기존 스키마 파일을 제자리에서 갱신한다. "
            f"먼저 {DEFAULT_TARGET.relative_to(ROOT)} 를 복사해 두고 --out 으로 지정할 것."
        )

    report = ingest(args.csv, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["seriesUnmapped"]:
        print(
            f"경고: 매핑되지 않은 구분 {report['seriesUnmapped']}건이 unmappedSeries 에 보존되었다. "
            "LABEL_RULES 를 보완할 것.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
