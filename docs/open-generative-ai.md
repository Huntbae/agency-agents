# Open Generative AI 분석 및 활용 가이드

> 분석 대상: <https://github.com/smirk-dev/Open-Generative-AI> (원본: [Anil-matcha/Open-Generative-AI](https://github.com/Anil-matcha/Open-Generative-AI), MIT 라이선스)
>
> 관련 문서: [Open Higgsfield AI 분석](./open-higgsfield-ai.md) — **같은 개발자의 이전 세대 프로젝트**입니다. 두 저장소 모두 Muapi.ai를 백엔드로 쓰지만, 이 프로젝트가 상위 호환 후속작이므로 실무에서는 이쪽을 우선 검토하세요.

Higgsfield AI·Freepik·Krea·OpenArt의 오픈소스 대안을 표방하는 AI 이미지·영상 생성 스튜디오입니다. 모델 200종 이상, 이미지-투-이미지·이미지-투-비디오·립싱크·노드 기반 워크플로우·로컬 온디바이스 추론까지 지원하며, 웹·데스크톱(Electron) 양쪽으로 배포됩니다.

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 정체 | Next.js 14 모노레포 기반 AI 생성 스튜디오 (웹 + Electron 데스크톱 앱) |
| 기술 스택 | Next.js 14 (App Router), React 18, Tailwind CSS v3, npm workspaces, Electron, stable-diffusion.cpp |
| AI 게이트웨이 | Muapi.ai (BYOK — 사용자 본인 키) |
| 로컬 추론 | stable-diffusion.cpp 내장 (데스크톱 앱 전용, API 키 불필요) |
| 배포 형태 | 자체 호스팅 / 호스팅판(dev.muapi.ai/open-generative-ai) / macOS·Windows·Linux 데스크톱 앱 v1.0.2 |
| 라이선스 | MIT |

### 이전 세대(Open Higgsfield AI)와의 차이 — 핵심

| 항목 | Open Higgsfield AI | **Open Generative AI** |
|------|------|------|
| 프레임워크 | Vite + Vanilla JS | Next.js 14 + React 18 모노레포 |
| 모델 수 | 약 90종 (T2I 49 + T2V 40) | **200종 이상** |
| 이미지-투-이미지 | 사실상 없음(일부 모델만) | **55종 이상, 참조 이미지 최대 14장** |
| 이미지-투-비디오 | 없음 | **60종 이상** |
| 립싱크 | 없음 | **9종 (초상화/영상 기반)** |
| 워크플로우 빌더 | 없음 | **Workflow Studio (노드 기반 + API 실행)** |
| 로컬 추론 | 없음 | **6개 모델 온디바이스 실행** |
| 폴링 타임아웃 | 2분 (2초×60) | **최대 30분 (2초×900)** — 장시간 영상 대응 |
| 데스크톱 앱 | 없음 | macOS/Windows/Linux 빌드 제공 |

**결론**: 이전 문서에서 한계로 지적했던 "참조 이미지 다중 입력 부재"와 "폴링 2분 타임아웃"이 이 프로젝트에서 모두 해결되었습니다. agency-agents의 콘텐츠 스킬(ai-ad, ai-influencer, asmr-mukbang)이 요구하는 **레퍼런스 이미지 기반 워크플로우**를 실제로 대체할 수 있는 것은 이쪽입니다.

## 2. 5개 스튜디오 구성

| 스튜디오 | 기능 | 모델 수 |
|------|------|------|
| **Image Studio** | 텍스트→이미지 / 이미지→이미지 듀얼 모드 | T2I 50+ / I2I 55+ |
| **Video Studio** | 텍스트→영상 / 이미지→영상 | T2V 40+ / I2V 60+ |
| **Lip Sync Studio** | 초상화 또는 영상 + 오디오 → 말하는 영상 | 9 |
| **Cinema Studio** | 카메라·렌즈·초점거리·조리개 등 촬영 파라미터 제어 | — |
| **Workflow Studio** | 노드 기반 다단계 파이프라인 빌더 + 커뮤니티 공유 | — |

### Lip Sync 모델

- **초상화 기반(이미지+오디오)**: Infinite Talk(480p/720p), Wan 2.2 Speech to Video(480p/720p), LTX 2.3 Lipsync(~1080p), LTX 2 19B Lipsync(~1080p)
- **영상 기반(영상+오디오)**: Sync Lipsync, LatentSync, Creatify Lipsync, Veed Lipsync, Infinite Talk V2V

## 3. 디렉토리 구조

```
Open-Generative-AI/
├── app/                          # Next.js App Router
│   ├── layout.js
│   └── studio/page.js            # → StandaloneShell
├── components/
│   ├── StandaloneShell.js        # 탭 네비게이션 + BYOK 처리
│   └── ApiKeyModal.js
├── packages/studio/src/          # 공유 React 컴포넌트 라이브러리 (핵심)
│   ├── models.js                 # 200+ 모델 정의 — 단일 정보원(single source of truth)
│   ├── muapi.js                  # API 클라이언트 (생성·업로드·워크플로우·에이전트)
│   ├── index.js
│   └── components/
│       ├── ImageStudio.jsx / VideoStudio.jsx
│       ├── LipSyncStudio.jsx / CinemaStudio.jsx
│       └── WorkflowStudio.jsx
├── electron/                     # 데스크톱 앱 + sd.cpp 연동
├── next.config.mjs               # transpilePackages 설정
└── tailwind.config.js
```

`packages/studio/src/models.js`를 수정하면 자체 호스팅판과 muapi.ai 호스팅판에 모두 반영되는 구조입니다.

## 4. 설치 및 실행

요구사항: **Node.js v18+**, **Muapi.ai API 키**(로컬 추론만 쓸 경우 불필요).

```bash
git clone https://github.com/smirk-dev/Open-Generative-AI.git
cd Open-Generative-AI
npm install
npm run dev            # http://localhost:3000
npm run build && npm run start   # 프로덕션
```

### 데스크톱 앱 빌드

```bash
npm run electron:build          # macOS DMG (Intel + Apple Silicon)
npm run electron:build:win      # Windows NSIS (x64 + ARM64)
npm run electron:build:linux    # Linux AppImage + .deb
npm run electron:build:all
# 산출물: release/
```

**macOS**: 서명되지 않은 앱이라 Gatekeeper가 차단합니다 — `xattr -cr "/Applications/Open Generative AI.app"` 실행 후 우클릭 → Open.
**Windows**: SmartScreen에서 More info → Run anyway.
**Ubuntu 24.04+**: AppImage가 AppArmor에 막히면 `.deb` 설치를 권장합니다.

## 5. 로컬 온디바이스 추론 (데스크톱 앱 전용)

stable-diffusion.cpp 엔진을 앱 내에서 1클릭 설치하고 모델 가중치를 내려받아 **API 키·네트워크 없이** 이미지를 생성합니다.

| 모델 | 타입 | 크기 | 스텝 |
|------|------|------|------|
| Z-Image Turbo | Diffusion Transformer | 2.5GB + 공유 2.7GB | 8 (고속) |
| Z-Image Base | Diffusion Transformer | 3.5GB + 공유 2.7GB | 50 (고품질) |
| Dreamshaper 8 | SD 1.5 | 2.1GB | 20 |
| Realistic Vision v5.1 | SD 1.5 | 2.1GB | 25 |
| Anything v5 | SD 1.5 | 2.1GB | 20 (애니메이션) |
| SDXL Base 1.0 | SDXL | 6.9GB | 30 |

Z-Image 계열 공유 파일: Qwen3-4B 텍스트 인코더(2.4GB) + FLUX VAE(335MB). **16GB RAM 권장**. macOS Apple Silicon은 Metal GPU 가속이 바이너리에 포함되어 있고, 그 외 플랫폼은 CPU 추론입니다.

사용 순서: 설정 → Local Models → sd.cpp 엔진 설치 → 모델 다운로드 → Image Studio에서 ⚡ Local 토글.

## 6. API 통신 구조

`packages/studio/src/muapi.js`가 모든 원격 호출을 담당합니다. 로컬 추론 분기는 이 파일이 아니라 Electron 계층에 있고, muapi.js는 전부 `https://api.muapi.ai`로 나갑니다.

- **인증**: 헤더 `x-api-key: <MUAPI_KEY>`, `Content-Type: application/json`
- **제출**: `POST /api/v1/{model-endpoint}`
- **폴링**: `GET /api/v1/predictions/{request_id}/result` — 2초 간격
  - 이미지: 최대 60회(2분) / **영상·I2V·립싱크: 최대 900회(약 30분)**
  - `completed`/`succeeded`/`success` → 반환, `failed`/`error` → 예외, 5xx는 재시도·4xx는 즉시 실패
- **파일 업로드**: `POST /api/v1/upload_file` (XHR + FormData, 진행률 콜백 지원). 응답의 `url`/`file_url`/`data.url` 중 하나를 호스팅 URL로 사용 → 이 URL을 I2I·I2V·립싱크 입력에 넣습니다.

### 주요 export 함수

```javascript
// 생성
generateImage(apiKey, params)      // T2I
generateI2I(apiKey, params)        // I2I (참조 이미지)
generateVideo(apiKey, params)      // T2V
generateI2V(apiKey, params)        // I2V
processLipSync(apiKey, params)     // 립싱크
generateMarketingStudioAd(apiKey, params)  // 광고 생성

// 파일·계정
uploadFile(apiKey, file, onProgress)
getUserBalance(apiKey)
calculateDynamicCost(apiKey, taskName, payload)   // 사전 비용 견적

// 워크플로우 (Muapi 서버 저장형)
createWorkflow / executeWorkflow / getUserWorkflows / getTemplateWorkflows
getPublishedWorkflows / getWorkflowInputs / getWorkflowData
runSingleNode / getNodeStatus / deleteNodeRun
```

### 모델 정의 스키마 (models.js)

```javascript
// Text-to-Image
{ id: "flux-dev", name: "Flux Dev", endpoint: "flux-dev-image",
  inputs: {
    prompt: { type: "string" },
    width:  { type: "int", default: 1024, minValue: 128, maxValue: 2048 },
    height: { type: "int", default: 1024 },
    num_images: { type: "int", default: 1, minValue: 1, maxValue: 4 },
  } }

// Image-to-Image — 참조 이미지 다중 입력
{ id: "flux-kontext-dev-i2i", name: "Flux Kontext Dev I2I",
  endpoint: "flux-kontext-dev-i2i",
  family: "kontext",
  imageField: "images_list",   // 모델별로 image_url / model_image_url 등으로 다름
  hasPrompt: true,
  maxImages: 10,               // Nano Banana 2 Edit은 14
  inputs: { ... } }
```

I2I 호출 시 이미지 파라미터 이름이 모델마다 다르므로 **반드시 `imageField`를 읽어서 payload 키를 정해야 합니다**. 개수 상한은 `maxImages`입니다.

### 재사용 예시 (Node.js)

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

async function poll(requestId, maxAttempts = 900, intervalMs = 2000) {
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

// I2V 예시: 업로드 → 제출 → 폴링
// const { url } = await uploadFile(...);              // POST /api/v1/upload_file
// const id = await submit("seedance-2.0-i2v", { prompt, image_url: url, duration: 5, resolution: "1080p" });
// const out = await poll(id);
```

## 7. agency-agents와의 연계 포인트

기존 콘텐츠 스킬(ai-ad, ai-influencer, asmr-mukbang)은 Higgsfield MCP(GPT Image + Seedance 2.0)를 호출합니다. 이 프로젝트는 같은 모델군을 REST로 노출하면서 **레퍼런스 이미지 다중 입력과 I2V까지 갖췄기 때문에**, 이전 세대와 달리 워크플로우를 통째로 대체할 수 있습니다.

1. **스킬 백업 파이프라인(실사용 가능)**: ai-ad의 "제품 누끼 + 모델 사진 → 광고 이미지 3장 → Seedance 5초 클립 4개" 흐름을 `uploadFile → generateI2I(images_list) → generateI2V(seedance-2.0-i2v)`로 1:1 대응 구현 가능. asmr-mukbang의 "모델 1장 + 음식 1장 → 먹방 스틸 → 영상"도 동일 패턴입니다.
2. **립싱크 확장**: 기존 스킬에 없는 기능입니다. ai-influencer로 만든 가상 인플루언서 프로필에 Infinite Talk / LTX 2.3을 붙이면 말하는 숏폼까지 확장됩니다.
3. **비용 사전 견적**: `calculateDynamicCost()`로 생성 전 크레딧 소모를 계산할 수 있어, 클라이언트 견적 산정·배치 실행 예산 관리에 바로 쓸 수 있습니다. `getUserBalance()`로 잔액 모니터링도 가능.
4. **로컬 추론 = 비용 0**: 시안·드래프트 단계 이미지를 Z-Image Turbo(8스텝)로 로컬 생성하고, 최종 컷만 유료 API로 뽑는 2단계 전략이 가능합니다.
5. **MCP 서버화 스펙**: `models.js`(모델·파라미터·imageField·maxImages)와 `muapi.js`(업로드·제출·폴링)가 그대로 Muapi MCP 서버의 설계 문서 역할을 합니다. `generate_image` / `generate_i2i` / `generate_video` / `generate_i2v` / `lipsync` 5개 도구로 감싸면 됩니다. mcp-builder 스킬과 조합하세요.
6. **Workflow Studio 엔진 분리 사용**: 노드 파이프라인 엔진은 [Vibe Workflow](https://github.com/SamurAIGPT/Vibe-Workflow)로 별도 오픈소스화되어 있어, 자체 서비스에 파이프라인 기능만 이식할 수 있습니다.

## 8. 한계 및 주의사항

- **"무료"의 범위**: 앱은 MIT 오픈소스지만 원격 생성은 Muapi.ai 크레딧(유료)을 씁니다. 실제로 무료인 것은 데스크톱 로컬 추론 6종뿐입니다.
- **"Uncensored" 표방**: 저장소가 "무검열"을 전면에 내세웁니다. 상업 프로젝트·클라이언트 납품물에 쓸 때는 **각 모델 제공사의 이용약관과 초상권·저작권 책임이 그대로 사용자에게 귀속**된다는 점을 유의해야 합니다. 브랜드 광고 제작에는 보수적으로 접근하세요.
- **키 보안**: BYOK 방식으로 API 키가 브라우저 localStorage에 저장됩니다. 공용 환경 배포 금지, 서버 사이드 전환 시 환경변수로 관리할 것.
- **포크의 최신성**: 분석 대상은 smirk-dev 포크(스타 6, 커밋 107)입니다. 활발히 갱신되는 쪽은 원본 Anil-matcha 저장소이므로, 실사용 시 **원본을 클론하고 포크는 참고용**으로 두는 편이 안전합니다.
- **모델 파라미터 문서 부재**: 모델별 허용값은 README에 없고 `packages/studio/src/models.js`가 사실상의 스펙입니다. 특히 I2I는 `imageField` 이름이 제각각이라 하드코딩하면 깨집니다.
- **로컬 추론 리소스**: Z-Image 계열은 가중치 7.4GB + 컴퓨트 버퍼 2.4GB로 16GB RAM이 필요하고, Apple Silicon 외에는 CPU 추론이라 느립니다.
- **데스크톱 앱 미서명**: macOS/Windows 모두 서명이 없어 사내 배포 시 보안 정책에 걸릴 수 있습니다.

## 참고 링크

- 분석 대상 포크: <https://github.com/smirk-dev/Open-Generative-AI>
- 원본 저장소: <https://github.com/Anil-matcha/Open-Generative-AI>
- 호스팅판: <https://dev.muapi.ai/open-generative-ai>
- 워크플로우 엔진: <https://github.com/SamurAIGPT/Vibe-Workflow>
- Muapi.ai: <https://muapi.ai>
