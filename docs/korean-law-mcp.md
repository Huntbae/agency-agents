# Korean Law MCP 설정 가이드

이 저장소에는 [korean-law-mcp](https://www.npmjs.com/package/korean-law-mcp) MCP 서버가 프로젝트 수준(`.mcp.json`)으로 등록되어 있습니다. Claude Code로 이 저장소를 열면 법제처 42개 API 기반의 한국 법령·판례 검색 도구 9개를 바로 사용할 수 있습니다.

## 제공 도구

| 도구 | 설명 |
|------|------|
| `search_law` | 법령명 키워드 검색 (약칭 자동변환, 시행예정 개정 병기) |
| `get_law_text` | 법령 조문 전문/특정 조문 조회 |
| `search_decisions` | 판례·해석례·헌재·행정심판 등 18개 도메인 통합 검색 |
| `get_decision_text` | 판례·결정문 본문 조회 |
| `get_annexes` | 별표·서식 조회 |
| `legal_research` | 다단계 법률 리서치 (8가지 task) |
| `legal_analysis` | 인용 검증, 판례 생사 확인, 행위시법 판단, 영향 그래프 |
| `discover_tools` | 전체 64개 세부 도구 탐색 |
| `execute_tool` | 세부 도구 직접 호출 |

## 사전 준비: 법제처 Open API 인증키(OC) 발급

1. [법제처 Open API 신청 페이지](https://open.law.go.kr/LSO/openApi/guideList.do)에서 회원가입 후 "Open API 사용 신청"을 합니다. (무료)
2. 발급받은 인증키(OC, 보통 가입 이메일의 아이디 부분)를 환경변수로 설정합니다.

```bash
# Mac/Linux (셸 프로필에 추가)
export LAW_OC=본인인증키
```

- **로컬 Claude Code**: 위 환경변수만 설정하면 `.mcp.json`이 자동으로 읽어갑니다.
- **Claude Code on the Web (원격 환경)**: 환경 설정의 Environment variables에 `LAW_OC`를 추가하세요.
- 키가 설정되지 않아도 서버는 기동되지만, 법제처 API 호출 시 인증 오류가 발생합니다.

## 사용 예시

Claude Code에서 자연어로 질문하면 도구가 자동 호출됩니다.

```
"근로기준법 제74조 알려줘"
"민법 제750조 인용한 판례 검증해줘"
"2023.5.10 당시 도로교통법 제44조는?"
```

## 참고

- 패키지: <https://www.npmjs.com/package/korean-law-mcp>
- 소스: <https://github.com/chrisryugj/korean-law-mcp>
- 설치 없이 claude.ai 커넥터로 쓰려면: `https://mcp.gomdori.app/law?oc=본인인증키`
