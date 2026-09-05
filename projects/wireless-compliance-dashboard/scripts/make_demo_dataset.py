#!/usr/bin/env python3
"""데모용 합성 데이터셋 생성기.

이 스크립트가 만드는 값은 전부 의사난수로 생성한 **가상의 수치**다. 실제 사업자의
허가·위반·납부 실적과는 아무 관계가 없으며, 대시보드의 UI·차트·집계 로직을
원자료 없이 점검하기 위한 용도로만 쓴다.

그래서 데모 프로파일의 사업자 라벨은 실명이 아니라 '이동통신사 A/B/C' 같은
익명 라벨을 쓴다. 합성 수치가 실존 기업 이름에 붙는 일이 없도록 하기 위한 것이다.

사용법:
    python3 scripts/make_demo_dataset.py
    -> data/carrier_metrics.demo.json 생성
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260905

PERIODS = ["2023", "2024", "2025", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
YEAR_PERIODS = {"2023", "2024", "2025"}

# (id, 익명 라벨, 사업자유형 코드, 규모 계수)
DEMO_CARRIERS = [
    ("DEMO_MNO_A", "이동통신사 A", "MNO", 1.00),
    ("DEMO_MNO_B", "이동통신사 B", "MNO", 0.82),
    ("DEMO_MNO_C", "이동통신사 C", "MNO", 0.61),
    ("DEMO_MVNO", "알뜰폰 사업자군", "MVNO", 0.18),
    ("DEMO_P5G", "이음5G 사업자군", "PRIVATE5G", 0.09),
    ("DEMO_PSN", "공공안전·전용망 기관군", "PS_NET", 0.14),
    ("DEMO_BCT", "지상파방송사업자군", "BC_TERR", 0.22),
    ("DEMO_SAT", "위성통신사업자군", "SAT_FSS", 0.07),
    ("DEMO_GEN", "간이·생활·아마추어 무선국", "GENERAL", 0.35),
]

# 지표별 (연간 기준값, 연도별 추세 계수, 월 환산 비율)
METRICS = {
    "licensedStations": {"base": 240_000, "trend": 1.06, "monthly": 1.0, "unit": "국"},
    "newLicenses": {"base": 18_000, "trend": 1.03, "monthly": 1 / 12, "unit": "건"},
    "techViolations": {"base": 42, "trend": 0.93, "monthly": 1 / 12, "unit": "건"},
    "licenseViolations": {"base": 27, "trend": 0.97, "monthly": 1 / 12, "unit": "건"},
    "spectrumFeeKRW1k": {"base": 9_800_000, "trend": 1.04, "monthly": 1 / 12, "unit": "천원"},
    "inspections": {"base": 3_400, "trend": 1.01, "monthly": 1 / 12, "unit": "건"},
}


def jitter(rng: random.Random, value: float, spread: float = 0.12) -> int:
    """값에 ±spread 범위의 흔들림을 준 뒤 정수로 반올림한다."""
    return max(0, round(value * rng.uniform(1 - spread, 1 + spread)))


def build() -> dict:
    rng = random.Random(SEED)
    carriers = []

    for cid, label, ctype, scale in DEMO_CARRIERS:
        series = {}
        for metric, spec in METRICS.items():
            # 설비를 보유하지 않는 유형은 무선국·검사·사용료 지표가 구조적으로 0이다.
            if ctype == "MVNO" and metric in {
                "licensedStations",
                "techViolations",
                "inspections",
                "spectrumFeeKRW1k",
            }:
                series[metric] = {p: 0 for p in PERIODS}
                continue
            # 국가·지자체 개설 무선국은 전파사용료가 전부 면제된다(전파법 제67조제1항제1호).
            if ctype == "PS_NET" and metric == "spectrumFeeKRW1k":
                series[metric] = {p: 0 for p in PERIODS}
                continue

            values = {}
            for idx, period in enumerate(sorted(YEAR_PERIODS)):
                annual = spec["base"] * scale * (spec["trend"] ** idx)
                values[period] = jitter(rng, annual)
            monthly_base = spec["base"] * scale * (spec["trend"] ** 3) * spec["monthly"]
            for period in PERIODS:
                if period in YEAR_PERIODS:
                    continue
                values[period] = jitter(rng, monthly_base, spread=0.18)
            series[metric] = values

        carriers.append(
            {"id": cid, "label": label, "type": ctype, "synthetic": True, "metrics": series}
        )

    return {
        "profile": "demo",
        "synthetic": True,
        "warning": "이 파일의 모든 수치는 의사난수로 생성한 가상값이다. 실제 사업자의 실적이 아니며 인용·보고에 사용해서는 안 된다.",
        "generator": "scripts/make_demo_dataset.py",
        "seed": SEED,
        "periods": PERIODS,
        "metricUnits": {k: v["unit"] for k, v in METRICS.items()},
        "carriers": carriers,
    }


if __name__ == "__main__":
    out = ROOT / "data" / "carrier_metrics.demo.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
