# 데이터 사전

이 디렉터리의 JSON 네 벌이 대시보드의 입력이다. `scripts/build_dashboard.py` 가
이들을 `index.html` 안으로 인라인한다.

| 파일 | 성격 | 채워지는 경로 |
|---|---|---|
| `rrb_national_stats.json` | 전국 총계 시계열 | `scripts/ingest_rrb_csv.py` |
| `tech_standards.json` | 기술기준 항목 × 사업자 유형 매핑 | 법령 조문 기준, 수기 유지 |
| `carriers.json` | 사업자 마스터(구조적 사실만) | 수기 유지 |
| `carrier_metrics.json` | 사업자별 실적 수치(공식) | 별도 원자료 투입 |
| `carrier_metrics.demo.json` | 사업자별 실적 수치(합성) | `scripts/make_demo_dataset.py` |

## rrb_national_stats

중앙전파관리소 전파관리통계(공공데이터포털 15054180)의 정규화본이다.

| 필드 | 설명 |
|---|---|
| `dataset` | 포털 목록 메타데이터(제공기관·형식·라이선스·갱신주기) |
| `ingestion.status` | `PENDING_INGEST` \| `INGESTED` |
| `periods[]` | `{key, label, granularity}` — `key` 는 `YYYY` 또는 `YYYY-MM` |
| `series[]` | `{id, label, group, unit, carrierAttributable, values}` |
| `series[].values` | `{기간키: 수치}`. 값이 없는 기간은 키 자체가 없다 |
| `series[].carrierAttributable` | 사업자 단위로 귀속시킬 수 있는 지표인지 여부 |
| `series[].sourceLabel` | 적재 시 원본 CSV의 '구분' 문자열(정본) |
| `unmappedSeries[]` | 매핑 규칙에 걸리지 않은 원본 행. **버리지 않고 보존한다** |

## tech_standards

| 필드 | 설명 |
|---|---|
| `legalBasis` | 상위법·기술규칙의 법령ID·MST·공포일·시행일·조회 경로 |
| `carrierTypes[]` | 사업자 유형. 개설 경로·단말 취급·검사 의무·전파사용료 지위를 조문과 함께 보유 |
| `standards[]` | 기술기준 항목. `applicability` 가 유형 코드 → `필수`/`조건부`/`해당없음` |
| `applicabilityLegend` | 세 값의 정의 |

`standards[].annex` 는 별표 번호만 담는다. **별표의 수치 자체는 담지 않는다** —
개정이 잦아 스냅샷이 곧 오답이 되기 때문이다.

## carrier_metrics

| 필드 | 설명 |
|---|---|
| `profile` | `official` \| `demo` |
| `synthetic` | `true` 면 화면 전체에 합성 데이터 경고가 걸린다 |
| `status` | `PENDING_INPUT` \| `LOADED` (official 전용) |
| `carriers[].metrics` | `{지표: {기간키: 수치\|null}}` |
| `carriers[].basis` | `{지표: OFFICIAL\|DERIVED\|ESTIMATED\|PENDING}` |

지표 키: `licensedStations`(국), `newLicenses`(건), `techViolations`(건),
`licenseViolations`(건), `spectrumFeeKRW1k`(천원), `inspections`(건).

`basis` 는 값과 짝을 이룬다. `ESTIMATED` 를 쓸 때에는 배분식과 근거 지표를
같은 객체에 남겨야 한다 — 추정치를 공표치처럼 읽는 것이 이 대시보드에서
가장 위험한 오독이다.
