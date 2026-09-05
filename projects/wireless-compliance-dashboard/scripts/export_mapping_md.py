#!/usr/bin/env python3
"""tech_standards.json -> docs/기술기준-매핑표.md.

매핑표를 손으로 다시 쓰면 대시보드와 문서가 어긋난다. 두 산출물이 같은 JSON을
쓰도록 문서를 생성한다.

사용법:
    python3 scripts/export_mapping_md.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "tech_standards.json"
OUT = ROOT / "docs" / "기술기준-매핑표.md"


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def build(ts: dict) -> str:
    types = ts["carrierTypes"]
    lines: list[str] = []
    a = lines.append

    a("# 기술기준 항목 × 사업자 유형 매핑표")
    a("")
    a("> 이 문서는 `scripts/export_mapping_md.py` 가 `data/tech_standards.json` 에서 생성한다.")
    a("> 직접 편집하지 말고 JSON을 고친 뒤 다시 생성할 것.")
    a("")
    lb = ts["legalBasis"]
    a(f"- 상위법: 「{lb['parentAct']['name']}」(법령ID {lb['parentAct']['lawId']}) "
      f"— 공포 {lb['parentAct']['promulgated']} · 시행 {lb['parentAct']['effective']}")
    a(f"- 기술규칙: 「{lb['technicalRule']['name']}」({lb['technicalRule']['issuer']}, "
      f"법령ID {lb['technicalRule']['lawId']}) — 공포 {lb['technicalRule']['promulgated']} "
      f"· 시행 {lb['technicalRule']['effective']}")
    a(f"- 조회 경로: {lb['retrievedVia']} · 조회일 {lb['retrievedAt']}")
    a("")

    a("## 1. 적용 매핑 매트릭스")
    a("")
    for key, desc in ts["applicabilityLegend"].items():
        a(f"- **{key}** — {desc}")
    a("")
    a("| 기술기준 항목 | 근거 조문 | " + " | ".join(t["shortLabel"] for t in types) + " |")
    a("|---|---|" + "---|" * len(types))
    for s in ts["standards"]:
        ref = s["legalRef"] + (f" · {s['annex']}" if s["annex"] not in ("-", "") else "")
        cells = [md_escape(s["applicability"].get(t["code"], "해당없음")) for t in types]
        a(f"| {md_escape(s['name'])} | {md_escape(ref)} | " + " | ".join(cells) + " |")
    a("")

    a("## 2. 기술기준 항목 상세 분류")
    a("")
    a("| ID | 분류 | 항목 | 측정 지표 | 정의 | 위임 구조 | 위반 시 영향 |")
    a("|---|---|---|---|---|---|---|")
    for s in ts["standards"]:
        a("| {id} | {cat} | {nm} | {ms} | {df} | {dg} | {vi} |".format(
            id=s["id"], cat=md_escape(s["category"]), nm=md_escape(s["name"]),
            ms=md_escape(s["measure"]), df=md_escape(s["definition"]),
            dg=md_escape(s["delegation"]), vi=md_escape(s["violationImpact"])))
    a("")

    a("## 3. 사업자 유형별 법적 지위")
    a("")
    a("| 사업자 유형 | 정의 | 무선국 개설 경로 | 가입자 단말 취급 | 전파사용료 | 산정 기준 |")
    a("|---|---|---|---|---|---|")
    for t in types:
        a("| **{lb}** | {df} | {op}<br>`{ob}` | {sr}<br>`{sb}` | {fs}<br>`{fb}` | {fa}<br>`{ab}` |".format(
            lb=md_escape(t["label"]), df=md_escape(t["definition"]),
            op=md_escape(t["openingRoute"]["route"]), ob=md_escape(t["openingRoute"]["basis"]),
            sr=md_escape(t["subscriberStationRoute"]["route"]),
            sb=md_escape(t["subscriberStationRoute"]["basis"]),
            fs=md_escape(t["spectrumFee"]["status"]), fb=md_escape(t["spectrumFee"]["basis"]),
            fa=md_escape(t["spectrumFee"]["assessment"]),
            ab=md_escape(t["spectrumFee"]["assessmentBasis"])))
    a("")

    a("## 4. 검사 의무")
    a("")
    a("| 사업자 유형 | 준공검사 | 정기검사 | 표본검사 |")
    a("|---|---|---|---|")
    for t in types:
        i = t["inspection"]
        a(f"| {md_escape(t['label'])} | {md_escape(i['준공검사'])} | "
          f"{md_escape(i['정기검사'])} | {md_escape(i['표본검사'])} |")
    a("")

    a("## 5. 읽을 때 주의할 점")
    a("")
    a("- 구체적 수치 기준(허용편차 값, 불요발사 허용치 등)은 무선설비규칙 **별표 1~6** 및 "
      "과학기술정보통신부 고시에 있다. 이 표는 항목·근거 조문·측정 지표·적용 대상까지만 정리하며 "
      "별표 수치를 옮겨 싣지 않는다. 별표는 개정이 잦으므로 판단에 쓸 때에는 조회 시점의 현행 별표를 확인해야 한다.")
    a("- '조건부'는 설비 유형·출력·전파형식 등 조건을 충족할 때만 적용된다는 뜻이며, "
      "면제를 뜻하지 않는다.")
    a("- 알뜰폰(MVNO)은 무선국 시설자가 아니므로 기술기준 준수 책임이 설비를 보유한 이동통신사업자에게 귀속된다. "
      "표의 '해당없음'은 이 귀속 구조를 나타낸 것이다.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(json.loads(SRC.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
