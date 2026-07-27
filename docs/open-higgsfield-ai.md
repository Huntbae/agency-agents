# Open Higgsfield AI 분석 및 활용 가이드

> 분석 대상: <https://github.com/sunnychase/open-higgsfield-ai> (원본: [Anil-matcha/Open-Higgsfield-AI](https://github.com/Anil-matcha/Open-Higgsfield-AI), MIT 라이선스)
>
> ⚠️ **후속작 있음**: 같은 개발자가 만든 [Open Generative AI](./open-generative-ai.md)가 상위 호환 버전입니다. 모델 200종+, 이미지-투-이미지·이미지-투-비디오·립싱크·로컬 추론을 지원하며, 이 문서 7장에서 지적한 한계(참조 이미지 다중 입력 부재, 폴링 2분 타임아웃)가 해결되어 있습니다. 실무 도입은 그쪽을 먼저 검토하세요. 이 문서는 구조가 단순해 Muapi 연동 패턴을 이해하는 입문 자료로 유효합니다.

Higgsfield AI의 무료 오픈소스 대안을 표방하는 웹 기반 AI 이미지·영상 생성 스튜디오입니다. 구독료 없이 [Muapi.ai](https://muapi.ai) API 키 하나로 이미지 모델 약 50종, 영상 모델 약 40종을 사용할 수 있습니다. 이 문서는 프로젝트 구조를 분석하고, 이 저장소(agency-agents)의 기존 Higgsfield MCP 기반 스킬(ai-ad, ai-influencer, asmr-mukbang)의 **대안/백업 파이프라인**으로 바로 활용할 수 있도록 정리한 가이드입니다.

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 정체 | 브라우저에서 동작하는 순수 프론트엔드 SPA (백엔드 없음) |
| 핵심 가치 | Higgsfield 유료 구독 없이 Muapi.ai 게이트웨이로 20+개 사 모델 접근 |
| 기술 스택 | Vite 5 + Vanilla JavaScript (프레임워크 없음) + Tailwind CSS v4 |
| AI 게이트웨이 | Muapi.ai — 단일 API 키·단일 요청 형식으로 멀티 모델 호출 |
| 데이터 저장 | API 키·생성 히스토리 모두 브라우저 localStorage (서버 전송 없음) |
| 라이선스 | MIT |

### 주요 기능

- **Image Studio**: 프롬프트 기반 이미지 생성 (최대 4K 다운로드)
- **Cinema Studio**: 카메라 6종·렌즈 11종·초점거리(8~85mm)·조리개(f/1.4~f/11) 등 촬영 파라미터를 프롬프트에 주입하는 시네마틱 이미지 생성
- **Video Studio**: Seedance·Kling·Veo·Sora 등 텍스트-투-비디오 생성
- **생성 히스토리**: localStorage 기반 이력 관리

## 2. 디렉토리 구조

```
open-higgsfield-ai/
├── src/
│   ├── components/
│   │   ├── AuthModal.js       # 최초 실행 시 Muapi 키 입력 모달
│   │   ├── Header.js / Sidebar.js / SettingsModal.js
│   │   ├── ImageStudio.js     # 기본 이미지 생성 UI
│   │   ├── CinemaStudio.js    # 카메라 제어 이미지 생성 UI
│   │   ├── CameraControls.js  # 카메라/렌즈/조리개 컨트롤
│   │   └── VideoStudio.js     # 영상 생성 UI
│   ├── lib/
│   │   ├── muapi.js           # Muapi API 클라이언트 (제출→폴링)
│   │   ├── models.js          # 모델 카탈로그 (t2iModels / t2vModels)
│   │   └── promptUtils.js     # 카메라 파라미터 → 프롬프트 변환
│   ├── styles/
│   └── main.js                # 진입점
├── package.json               # vite / tailwindcss v4 / puppeteer
└── README.md
```

## 3. 설치 및 실행

요구사항: **Node.js v18+**, **Muapi.ai API 키**([muapi.ai](https://muapi.ai) 가입 후 발급, 크레딧 기반 과금).

```bash
git clone https://github.com/sunnychase/open-higgsfield-ai.git
cd open-higgsfield-ai
npm install
npm run dev        # http://localhost:5173
# 배포용: npm run build && npm run preview
```

첫 접속 시 AuthModal에서 Muapi API 키를 입력하면 localStorage(`muapi_key`)에 저장됩니다. `.env` 설정은 없으며 키는 전적으로 브라우저에만 보관됩니다.

## 4. API 통신 구조 (핵심)

`src/lib/muapi.js`의 동작 방식은 **제출(Submit) → 폴링(Poll)** 2단계입니다. 이 패턴만 이해하면 UI 없이도 스크립트/에이전트에서 직접 재사용할 수 있습니다.

- **베이스 URL**: `https://api.muapi.ai` (개발 모드에선 Vite 프록시로 상대경로 사용)
- **인증**: 요청 헤더 `x-api-key: <MUAPI_KEY>`
- **제출**: `POST /api/v1/{model-endpoint}` — body에 `prompt` + 모델별 파라미터
- **폴링**: `GET /api/v1/predictions/{request_id}/result` — 기본 2초 간격 × 최대 60회(약 2분)
- **상태 판별**: `completed`/`succeeded`/`success` → 결과 반환, `failed`/`error` → 예외, 그 외(`processing`/`pending`) → 계속 폴링. 5xx는 재시도, 4xx는 즉시 실패.

### curl로 직접 호출하는 예시

```bash
# 1) 이미지 생성 제출 (Flux Dev 예시)
curl -s -X POST "https://api.muapi.ai/api/v1/flux-dev-image" \
  -H "x-api-key: $MUAPI_KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "K-beauty product on marble, soft studio light", "width": 1024, "height": 1024, "num_images": 1}'
# 응답의 request_id(또는 id) 확보

# 2) 결과 폴링
curl -s "https://api.muapi.ai/api/v1/predictions/{request_id}/result" \
  -H "x-api-key: $MUAPI_KEY"
```

### Node.js 재사용 예시 (muapi.js 패턴 이식)

```javascript
const BASE = "https://api.muapi.ai";
const KEY = process.env.MUAPI_KEY;

async function submit(endpoint, payload) {
  const res = await fetch(`${BASE}/api/v1/${endpoint}`, {
    method: "POST",
    headers: { "x-api-key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`submit ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.request_id ?? data.id;
}

async function poll(requestId, maxAttempts = 60, intervalMs = 2000) {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await fetch(`${BASE}/api/v1/predictions/${requestId}/result`, {
      headers: { "x-api-key": KEY },
    });
    if (res.ok) {
      const data = await res.json();
      const s = (data.status || "").toLowerCase();
      if (["completed", "succeeded", "success"].includes(s)) return data;
      if (["failed", "error"].includes(s)) throw new Error(JSON.stringify(data));
    } else if (res.status < 500) {
      throw new Error(`poll ${res.status}`);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("polling timed out");
}

// 사용: const id = await submit("seedance-pro-t2v", { prompt, aspect_ratio: "9:16", duration: 5, resolution: "1080p" });
//       const result = await poll(id);
```

## 5. 지원 모델 카탈로그

전체 목록은 `src/lib/models.js`에 정의되어 있습니다 (`t2iModels` 약 49종, `t2vModels` 약 40종). 실무 관점의 주요 모델만 추리면:

### 이미지 (Text-to-Image)

| 용도 | 모델 (endpoint id) | 주요 파라미터 |
|------|------|------|
| 초고속 드래프트 | `flux-schnell`, `z-image-turbo` | prompt, width/height |
| 범용 고품질 | `flux-dev`, `flux-2-pro`, `bytedance-seedream-v4.5` | prompt, aspect_ratio, resolution/quality |
| GPT 계열 | `gpt4o-text-to-image`, `gpt-image-1.5` | prompt, aspect_ratio, quality, num_images |
| 구글 계열 | `google-imagen4`(-fast/-ultra) | prompt, aspect_ratio |
| 미드저니 | `midjourney-v7-text-to-image` | speed, variety, stylization, weirdness |
| 스타일/편집 | `ideogram-v3-t2i`, `flux-kontext-pro-t2i`, `flux-pulid`(얼굴 참조), `flux-redux`(이미지 참조) | image_url, style 등 |

### 영상 (Text-to-Video)

| 용도 | 모델 (endpoint id) | 주요 파라미터 |
|------|------|------|
| Seedance (스킬 호환) | `seedance-pro-t2v`, `seedance-v1.5-pro-t2v`(+fast) | prompt, aspect_ratio, duration, resolution |
| Kling | `kling-v2.6-pro-t2v`, `kling-v3.0-pro-text-to-video` | prompt, aspect_ratio, duration |
| Google Veo | `veo3.1-text-to-video`(+fast) | prompt, aspect_ratio, duration, resolution |
| OpenAI Sora | `openai-sora-2-text-to-video`, `openai-sora-2-pro-text-to-video` | prompt, aspect_ratio, duration |
| 가성비 | `wan2.6-text-to-video`, `pixverse-v5.5-t2v`, `minimax-hailuo-2.3-standard-t2v` | prompt, duration, resolution |

공통 파라미터 규칙: 이미지 모델은 `width/height` 또는 `aspect_ratio`(+`resolution`) 중 하나를 쓰고, 영상 모델은 대체로 `aspect_ratio`(16:9 / 9:16 / 1:1) + `duration`(5~10초) + `resolution`(480p~1080p)을 받습니다.

## 6. 이 저장소(agency-agents)와의 연계 포인트

기존 콘텐츠 제작 스킬들은 **Higgsfield MCP**(GPT Image + Seedance 2.0)를 호출합니다. Open Higgsfield AI가 쓰는 **Muapi.ai**는 동일 계열 모델(`gpt-image-1.5`, `gpt4o-text-to-image`, `seedance-*`)을 REST로 노출하므로, 다음과 같이 활용할 수 있습니다.

1. **백업 파이프라인**: Higgsfield MCP 크레딧 소진·장애 시, 위 4장의 submit→poll 패턴으로 동일 워크플로(ai-ad의 이미지 3장 + 영상 4클립, asmr-mukbang의 스틸+영상)를 Muapi로 대체 실행.
2. **모델 벤치마킹**: 같은 프롬프트를 Flux 2 Pro / Seedream 4.5 / Imagen4 / Midjourney v7에 병렬 제출해 광고 컷 품질 비교. 단일 키·단일 요청 형식이라 비교 스크립트가 단순함.
3. **로컬 스튜디오 UI**: 클라이언트에게 프롬프트 시안을 직접 만지게 할 때 `npm run dev`로 띄워 시연용 UI로 사용 (설치 3분, 백엔드 불필요).
4. **MCP 서버화 참고 자료**: `models.js`의 모델 카탈로그 + `muapi.js`의 폴링 로직은 그대로 Muapi MCP 서버(도구: `generate_image`, `generate_video`)를 만들 때의 스펙 문서 역할을 함. mcp-builder 스킬과 조합 가능.

## 7. 한계 및 주의사항

- **무료가 아님**: 앱 자체는 무료·오픈소스지만 Muapi.ai는 크레딧 기반 유료 API입니다. "Higgsfield 구독 대비 종량제"로 이해해야 합니다.
- **키 보안**: API 키가 브라우저 localStorage에 평문 저장됩니다. 공용 PC·배포 환경에서는 사용 금지. 서버 사이드로 옮길 경우 키를 환경변수로 관리할 것.
- **CORS/프록시**: 프로덕션 빌드에서 브라우저가 `api.muapi.ai`를 직접 호출하므로, 자체 배포 시 프록시 구성이 필요할 수 있습니다.
- **이미지 투 이미지 제한**: image_url을 받는 모델(`flux-pulid`, `flux-redux`, `z-image-base` 등)이 일부 있으나, Higgsfield MCP처럼 레퍼런스 이미지 다중 입력 워크플로가 정형화되어 있지는 않습니다.
- **폴링 타임아웃**: 기본 2분(2초×60회)이라 고해상도 영상 모델(Sora 2 Pro 등)은 타임아웃될 수 있음 — 재사용 시 `maxAttempts`를 늘려서 사용할 것.
- **문서 부족**: 모델별 정확한 파라미터 허용값은 README에 없고 `models.js` 소스가 사실상의 스펙입니다.

## 참고 링크

- 분석 대상 포크: <https://github.com/sunnychase/open-higgsfield-ai>
- 원본 저장소: <https://github.com/Anil-matcha/Open-Higgsfield-AI>
- Muapi.ai: <https://muapi.ai>
