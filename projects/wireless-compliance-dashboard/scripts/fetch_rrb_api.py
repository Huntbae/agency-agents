#!/usr/bin/env python3
"""공공데이터포털 오픈API로 전파관리통계를 받아 data/rrb_national_stats.json 에 적재한다.

CSV를 손으로 내려받는 대신 인증키로 직접 받아오는 경로다. 정규화 규칙은
scripts/rrb_common.py 를 공유하므로 CSV 경로와 결과가 같다.

준비
----
1. 공공데이터포털에서 해당 데이터의 활용신청을 하고 인증키를 발급받는다.
   발급된 키는 마이페이지 > 개발계정 상세보기에서 확인한다.
   https://www.data.go.kr/iim/api/selectAPIAcountView.do
2. 같은 화면에서 '데이터명 / 엔드포인트 / 상세기능'의 요청 주소를 확인해
   `/api/...` 이후 경로를 그대로 --path 로 넘긴다(파일데이터 오픈API는
   `15054180/v1/uddi:...` 형태다). uddi 값은 데이터마다 다르고 포털 화면에만
   표시되므로 추측할 수 없다.
3. 인증키는 환경변수로만 다룬다. 저장소에 넣지 않는다.

    export DATA_GO_KR_SERVICE_KEY='발급받은 일반 인증키(Decoding)'
    python3 scripts/fetch_rrb_api.py --path '15054180/v1/uddi:xxxxxxxx-xxxx-xxxx'

인증키 두 가지 형태 주의
------------------------
포털은 같은 키를 Encoding 형태와 Decoding 형태로 함께 보여준다. 이 스크립트는
기본적으로 **Decoding 키**를 받아 한 번만 URL 인코딩한다. Encoding 키를 그대로
넣으면 `%2B` 가 `%252B` 로 이중 인코딩되어 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가
난다. Encoding 키밖에 없다면 --key-is-encoded 를 붙여 그대로 실어 보낸다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rrb_common import DEFAULT_TARGET, ROOT, apply_rows  # noqa: E402

# 기본값은 포털 엔드포인트. RRB_API_BASE 로 덮어쓸 수 있게 둔 것은 로컬 스텁 서버로
# 페이지네이션·오류 처리를 검증하기 위해서다(운영에서는 설정하지 않는다).
BASE_URL = os.environ.get("RRB_API_BASE", "https://api.odcloud.kr/api").rstrip("/")
KEY_ENV = "DATA_GO_KR_SERVICE_KEY"
PATH_ENV = "RRB_API_PATH"
TIMEOUT = 30

# 포털이 자주 돌려주는 오류코드 -> 실제로 해야 할 조치.
ERROR_HINTS = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR":
        "인증키가 등록되지 않았습니다. 활용신청 승인 여부를 확인하고, Encoding 키를 쓰고 있다면 "
        "--key-is-encoded 를 붙이거나 Decoding 키로 바꾸십시오(이중 인코딩이 가장 흔한 원인입니다).",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR":
        "일일 트래픽 한도를 초과했습니다. 개발계정은 기본 한도가 낮습니다. 내일 다시 시도하거나 "
        "운영계정으로 상향 신청하십시오.",
    "SERVICE_ACCESS_DENIED_ERROR":
        "해당 인증키로 이 데이터에 접근할 권한이 없습니다. 이 데이터의 활용신청이 승인되었는지 확인하십시오.",
    "DEADLINE_HAS_EXPIRED_ERROR":
        "활용기간이 만료되었습니다. 포털에서 연장 신청하십시오.",
    "NO_OPENAPI_SERVICE_ERROR":
        "해당 경로에 오픈API가 없습니다. --path 의 uddi 값을 포털 화면의 요청 주소와 대조하십시오. "
        "이 데이터가 파일데이터 전용이면 오픈API 자체가 제공되지 않을 수 있습니다.",
    "HTTP_ERROR":
        "요청 형식이 거부되었습니다. --path 와 파라미터를 포털 문서와 대조하십시오.",
}


def redact(text: str, secret: str) -> str:
    """로그·오류 메시지에서 인증키를 지운다. 키가 밖으로 새면 안 된다."""
    if not secret:
        return text
    out = text.replace(secret, "***REDACTED***")
    return out.replace(urllib.parse.quote(secret, safe=""), "***REDACTED***")


def build_url(path: str, page: int, per_page: int, key: str, key_is_encoded: bool,
              use_header: bool) -> str:
    params = {"page": str(page), "perPage": str(per_page), "returnType": "JSON"}
    query = urllib.parse.urlencode(params)
    if not use_header:
        # Decoding 키는 여기서 한 번만 인코딩된다. Encoding 키는 이미 인코딩된
        # 상태이므로 그대로 붙인다 — 다시 인코딩하면 이중 인코딩이 된다.
        service_key = key if key_is_encoded else urllib.parse.quote(key, safe="")
        query = f"{query}&serviceKey={service_key}"
    return f"{BASE_URL}/{path.lstrip('/')}?{query}"


def request_page(url: str, key: str, use_header: bool) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if use_header:
        req.add_header("Authorization", f"Infuser {key}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        raise SystemExit(
            f"HTTP {exc.code} 응답:\n{redact(body, key)}\n\n"
            + describe_error(body)
        ) from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"연결 실패: {exc.reason}\n"
            "이 환경의 아웃바운드 프록시가 api.odcloud.kr 을 차단하고 있다면 "
            "네트워크가 열린 곳에서 실행해야 합니다."
        ) from None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 포털은 JSON 엔드포인트에서도 오류를 XML로 돌려주는 경우가 있다.
        raise SystemExit(
            f"JSON이 아닌 응답:\n{redact(raw[:600], key)}\n\n" + describe_error(raw)
        ) from None


def describe_error(body: str) -> str:
    for code, hint in ERROR_HINTS.items():
        if code in body:
            return f"[{code}] {hint}"
    return ("응답 본문에서 알려진 오류코드를 찾지 못했습니다. "
            "포털의 해당 API 문서와 요청 주소를 대조하십시오.")


def fetch_all(path: str, key: str, per_page: int, key_is_encoded: bool,
              use_header: bool) -> list[dict]:
    rows: list[dict] = []
    page, total = 1, None
    while True:
        url = build_url(path, page, per_page, key, key_is_encoded, use_header)
        payload = request_page(url, key, use_header)
        chunk = payload.get("data") or []
        rows.extend(chunk)
        if total is None:
            total = payload.get("totalCount", len(chunk))
            print(f"totalCount={total}")
        print(f"  page {page}: {len(chunk)}행 (누적 {len(rows)})")
        if not chunk or len(rows) >= total or page > 100:
            break
        page += 1
    if total is not None and len(rows) != total:
        print(f"경고: totalCount({total})와 수신 행수({len(rows)})가 다릅니다.", file=sys.stderr)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="전파관리통계 오픈API 적재")
    ap.add_argument("--path", default=os.environ.get(PATH_ENV),
                    help=f"api.odcloud.kr/api 이후 경로 (환경변수 {PATH_ENV} 로도 지정 가능)")
    ap.add_argument("--out", type=Path, default=DEFAULT_TARGET, help="적재 대상 JSON")
    ap.add_argument("--per-page", type=int, default=100, help="페이지당 행수 (기본 100)")
    ap.add_argument("--key-is-encoded", action="store_true",
                    help="Encoding 형태 인증키를 그대로 실어 보낸다(이중 인코딩 방지)")
    ap.add_argument("--auth", choices=("query", "header"), default="query",
                    help="인증 방식: query=serviceKey 파라미터, header=Authorization: Infuser")
    ap.add_argument("--dry-run", action="store_true",
                    help="요청 URL만 출력하고 끝낸다(인증키는 가려서 출력)")
    args = ap.parse_args()

    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"환경변수 {KEY_ENV} 가 비어 있습니다.\n"
            "공공데이터포털 마이페이지 > 개발계정 상세보기에서 일반 인증키를 확인해 설정하십시오.\n"
            "  https://www.data.go.kr/iim/api/selectAPIAcountView.do\n"
            f"  export {KEY_ENV}='발급받은 Decoding 인증키'\n"
            "인증키는 저장소에 커밋하지 마십시오."
        )
    if not args.path:
        raise SystemExit(
            f"--path 가 필요합니다(또는 환경변수 {PATH_ENV}).\n"
            "포털의 해당 API 요청 주소에서 `/api/` 뒤 경로를 그대로 넘기십시오. 예:\n"
            "  --path '15054180/v1/uddi:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'\n"
            "uddi 값은 데이터마다 다르고 포털 화면에만 표시되므로 추측할 수 없습니다."
        )

    use_header = args.auth == "header"
    if args.dry_run:
        url = build_url(args.path, 1, args.per_page, key, args.key_is_encoded, use_header)
        print(redact(url, key))
        if use_header:
            print("Authorization: Infuser ***REDACTED***")
        return 0

    if not args.out.exists():
        raise SystemExit(
            f"적재 대상 JSON이 없다: {args.out}\n"
            f"먼저 {DEFAULT_TARGET.relative_to(ROOT)} 를 복사해 두고 --out 으로 지정할 것."
        )

    rows = fetch_all(args.path, key, args.per_page, args.key_is_encoded, use_header)
    if not rows:
        raise SystemExit("응답에 데이터 행이 없습니다. --path 와 활용신청 상태를 확인하십시오.")

    # 열 순서는 첫 행 기준으로 잡되, 뒤쪽 행에만 있는 열도 빠뜨리지 않는다.
    headers: list[str] = []
    for row in rows:
        for k in row:
            if k not in headers:
                headers.append(k)

    doc = json.loads(args.out.read_text(encoding="utf-8"))
    report = apply_rows(doc, headers, rows, {
        "sourceApiPath": args.path,
        "tool": "scripts/fetch_rrb_api.py",
    })
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
