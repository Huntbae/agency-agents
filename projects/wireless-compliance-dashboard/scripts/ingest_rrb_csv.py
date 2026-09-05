#!/usr/bin/env python3
"""중앙전파관리소 전파관리통계 CSV -> data/rrb_national_stats.json 정규화 적재기.

원본(공공데이터포털 15054180)은 가로형 표다. 1열이 '구분', 나머지가
'2023년', '2024년', '2025년', '2026년1월' … 같은 기간 열이다.

'구분' 라벨 매핑과 숫자·기간 파싱은 scripts/rrb_common.py 에 있다. 오픈API
경로(fetch_rrb_api.py)와 같은 규칙을 쓰기 위해서다.

사용법:
    python3 scripts/ingest_rrb_csv.py 전파관리통계_20260531.csv
    python3 scripts/ingest_rrb_csv.py 전파관리통계.csv --out data/rrb_national_stats.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rrb_common import DEFAULT_TARGET, ROOT, apply_rows  # noqa: E402

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8")


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


def ingest(csv_path: Path, target: Path) -> dict:
    table = read_rows(csv_path)
    if not table:
        raise SystemExit(f"빈 CSV: {csv_path}")

    header, *body = table
    headers = [h.strip() for h in header]
    rows = [dict(zip(headers, row)) for row in body]

    doc = json.loads(target.read_text(encoding="utf-8"))
    report = apply_rows(doc, headers, rows, {"sourceFile": csv_path.name,
                                             "tool": "scripts/ingest_rrb_csv.py"})
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


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
            "rrb_common.py 의 LABEL_RULES 를 보완할 것.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
