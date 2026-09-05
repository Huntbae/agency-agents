#!/usr/bin/env python3
"""templates/dashboard.body.html + data/*.json -> index.html (단일 파일 대시보드).

데이터를 JSON으로 따로 두면서도 결과물은 의존성 없는 단일 HTML이어야 해서,
빌드 시점에 JSON을 <script type="application/json"> 안으로 인라인한다.

산출물 두 벌:
  index.html                     완전한 HTML 문서 — 브라우저에서 바로 열린다
  artifact/dashboard.body.html   <head>/<body> 없는 본문 조각 — Artifact 게시용

사용법:
    python3 scripts/build_dashboard.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "dashboard.body.html"
PLACEHOLDER = "/*__DATA__*/"

SOURCES = {
    "national": "rrb_national_stats.json",
    "carriers": "carriers.json",
    "techStandards": "tech_standards.json",
    "metricsOfficial": "carrier_metrics.json",
    "metricsDemo": "carrier_metrics.demo.json",
}


def load_data() -> dict:
    return {key: json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
            for key, name in SOURCES.items()}


def inline_safe(payload: dict) -> str:
    """JSON을 <script> 블록에 안전하게 넣는다.

    HTML 파서는 스크립트 본문에서 '</script' 를 만나면 블록을 끝낸다. 데이터에
    그런 문자열이 있으면 문서가 깨지므로 '<' 를 유니코드 이스케이프로 바꾼다.
    JSON 문자열 안에서 \\u003c 는 '<' 와 동일하게 파싱되므로 값은 보존된다.
    """
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def build() -> tuple[Path, Path]:
    body = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in body:
        raise SystemExit(f"템플릿에 {PLACEHOLDER} 자리표시자가 없다: {TEMPLATE}")
    body = body.replace(PLACEHOLDER, inline_safe(load_data()))

    fragment = ROOT / "artifact" / "dashboard.body.html"
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text(body, encoding="utf-8")

    document = ROOT / "index.html"
    document.write_text(
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<style>:root{color-scheme:light dark}body{margin:0}"
        "img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n",
        encoding="utf-8",
    )
    return document, fragment


if __name__ == "__main__":
    doc, frag = build()
    for path in (doc, frag):
        print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
