# mvstudio 설계 문서

로컬 우선(local-first) 뮤직비디오 생성 스튜디오 — "뮤직비디오 전용 ComfyUI/Draw Things".
2026-07 설계 검토 결과 요약. 허용 라이선스 기준: **MIT/BSD/ISC/Apache-2.0 (상용 클로즈드소스 배포 가능)**.

## 1. 왜 하이브리드 엔진인가

3~4분 곡 전체를 영상 확산 모델로 생성하는 것은 Mac 로컬에서 시간·메모리 모두 비현실적이다.
반면 비트 싱크 컷 편집, 카메라 모션(Ken Burns), 트랜지션, 컬러 그레이딩은 FFmpeg/Metal로
실시간급 처리가 되고, "곡에 어울리는 느낌"의 대부분이 여기서 나온다. 따라서:

> **연출·편집 엔진이 본체, AI 생성(이미지/짧은 클립)은 양념.**
> LLM의 역할은 영상을 그리는 것이 아니라 감독(연출 결정)이다.

## 2. 핵심 계약: 스토리보드 JSON

감독(rule/LLM 무엇이든)의 출력은 스토리보드 JSON 하나로 수렴하고, 렌더러는 그 JSON만 읽는
결정적 엔진이다. 이 분리가 보장하는 것:

- 모델 교체 자유 (rule ↔ Qwen3 ↔ 미래 모델) — 렌더 품질 불변
- 편집 UI(타임라인)가 JSON 편집기로 자연스럽게 성립
- LLM 출력은 항상 sanitizer(비트 스냅, 연속성 강제)를 통과 → 나쁜 모델은 품질을 떨어뜨릴 수는 있어도 렌더를 깨뜨릴 수 없음
- 워크플로 공유/템플릿/커뮤니티 프리셋의 단위 (ComfyUI의 workflow.json에 해당)

## 3. 제품 아키텍처

```
┌─ UI 층 (Phase 1+) ────── 타임라인 편집기 (파형+비트그리드+컷 카드). 노드 UI는 고급 모드로 후순위
├─ MCP 서버 (Phase 0.5) ── analyze_song / generate_storyboard / apply_preset / render
│                          → Claude 등 에이전트가 UI 역할. Higgsfield MCP의 로컬 대응물
├─ Model Manager ───────── 앱 내 다운로드, RAM 감지 → 양자화 선택 → 기능 게이팅
├─ Engine Core (이 MVP) ── 스토리보드 JSON 해석, 스테이지 스케줄러(순차 로드/언로드), 잡 큐
└─ 러너 ────────────────── librosa │ whisper.cpp │ Qwen3-VL(MLX) │ mflux │ mlx-video │ FFmpeg
```

**참조 앱 라이선스 경계**: ComfyUI(GPL-3.0), Draw Things community(GPL-v3) 코드는 재사용 불가.
UX·설계 사상만 참조, 엔진은 자체 구현 (러너 스택이 전부 MIT라 가능).

## 4. 카메라 프리셋 3계층

프리셋은 코드가 아닌 데이터(`presets/camera_presets.json`). 각 프리셋이 계층별 구현과
RAM 폴백 체인을 선언한다.

| 계층 | 구현 | 속도 | 예시 | 최소 RAM |
|---|---|---|---|---|
| T1 2D 결정적 | FFmpeg zoompan (이 MVP) | 실시간급 | zoom/pan/tilt/ken burns | 전 사양 |
| T2 2.5D 패럴랙스 | Depth Anything V2 **Small**(Apache) 깊이맵 → 메쉬 워프 | 컷당 수 초 | dolly, dolly zoom(버티고), 소각도 orbit | 16GB |
| T3 생성형 | Wan2.2 Fun Camera Control(Apache), 카메라 코드 조건 | 클립당 수 분 | FPV drone, 360 orbit, through-object | 32GB |

참고: Higgsfield의 카메라 컨트롤도 Wan 기반 — T3의 기반 기술은 동일 계열이다.

## 5. 사양 티어 (Apple Silicon 유니파이드 메모리)

순차 실행 + 스테이지별 모델 언로드 → 필요 메모리는 합계가 아닌 **최대 단계**.

| 스테이지 | 모델 | 피크 |
|---|---|---|
| 오디오 분석 | librosa | <1GB |
| 가사 STT | whisper large-v3-turbo | ~2GB |
| 이미지 이해+감독 | Qwen3-VL-8B 4bit (겸용 1모델) | ~6GB |
| 보충 이미지 | FLUX.2-klein-4B | ~6–8GB |
| AI 클립 | Wan2.2 TI2V-5B (FP8 8–10GB+인코더) | ~12–16GB |
| 고품질 클립 | LTX-2.3 (Q4 ~19.4GB) | 20GB+ |

- **최소 16GB**: 분석+가사+감독+비트싱크 렌더+FLUX.2-klein 이미지. AI 영상 클립 비활성(게이팅)
- **권장 32GB**: 전 기능 (Wan2.2 5B 클립). LTX-2.3은 단독 배치 모드만
- **프로 48–64GB+**: LTX-2.3 상시, 스테이지 병렬, 14B급
- **디스크**: 모델 풀 세트 20–40GB + 작업 공간 → 여유 60GB 권장

## 6. 라이선스 매트릭스 (상용 배포 판정, 2026-07 검증)

| 구성 요소 | 라이선스 | 판정 / 주의 |
|---|---|---|
| librosa | ISC | ✅ |
| whisper.cpp + Whisper 가중치 | MIT | ✅ |
| Qwen3 / Qwen3-VL | Apache-2.0 | ✅ (Qwen2.5-VL은 3B 비상용·72B Qwen 라이선스 — 사이즈 함정) |
| Ollama / llama.cpp / MLX / mlx-video / mflux | MIT | ✅ |
| Wan2.1 / Wan2.2 / Wan2.2-Fun-Camera | Apache-2.0 | ✅ 생성물 권리 주장 없음 |
| LTX-2.3 | Apache-2.0 | ✅ (LTX-2 구버전은 ARR $10M 제한 — 2.3만 사용) |
| FLUX.2-klein-**4B** / FLUX.1-schnell | Apache-2.0 | ✅ (**klein-9B·FLUX.1-dev는 비상용**) |
| Depth Anything V2 **Small** | Apache-2.0 | ✅ (**Base/Large/Giant는 CC BY-NC**) |
| FFmpeg | LGPL 2.1+ | ⚠️ LGPL 빌드만, libx264/265 금지, videotoolbox 인코더 사용. Homebrew 빌드는 GPL |
| libass / Pretendard·Noto Sans KR | ISC / OFL | ✅ (가사 자막용) |
| Tauri → SwiftUI | MIT·Apache → — | ✅ |
| MCP SDK | MIT | ✅ |
| **사용 금지** | | ComfyUI·Draw Things 코드(GPL), madmom 모델(CC BY-NC), Essentia(AGPL), aubio(GPL), EXAONE(NC), HunyuanVideo(커스텀) |

## 7. 로드맵

1. **Phase 0 (완료 — 이 MVP)**: CLI 엔진 코어, 스토리보드 JSON 스키마, rule/ollama 감독, T1 프리셋 12종, FFmpeg 렌더러, e2e 테스트
2. **Phase 0.5 (완료)**: 로컬 MCP 서버 (`mvstudio-mcp`, stdio) — 6개 도구 노출, 실제 JSON-RPC 교환으로 e2e 검증. GUI보다 먼저 출시 가능한 카드 (Claude가 UI)
3. **Phase 2a (완료)**: 리릭 비디오 모드 — LRC 파싱 + Pillow→overlay 자막 번인(어떤 FFmpeg 빌드든 동작, 한글 폰트 자동 감지), `mvstudio transcribe`(faster-whisper, 선택 설치; 모델 호출부는 Mac에서 검증 필요), 구간별 컬러 그레이딩(데이터 정의) + 구간 경계 딥 트랜지션
4. **Phase 2b-1 (완료)**: 의미 매칭 — Ollama 비전 모델(Qwen3-VL)이 사진 내용을 캡션/태그로 파악하고, 텍스트 모델이 가사·구간 에너지와 대조해 무관한 사진을 제외하고 구간별 풀을 배정. sanitizer가 모델 오출력(전체 제외, 잘못된 인덱스)을 방어. 미가용 시 energy 매칭 폴백
5. **Phase 2b-2 (완료)**: 가사→이미지 생성 — 구간·가사에서 장면 프롬프트 생성(LLM 또는 오프라인 템플릿 폴백) → mflux/FLUX.2-klein-4B로 구간별 이미지 생성 → 정확한 구간 풀로 편집. `--visuals generate`. mflux 호출부는 얇은 래퍼(맥 실기 검증 필요)
6. **Phase 1**: Tauri 타임라인 UI + 모델 매니저(RAM 게이팅)
5. **Phase 3**: Wan2.2 클립 생성(백그라운드 큐+저해상도 프리뷰), T2/T3 프리셋
6. **Phase 4**: SwiftUI+AVFoundation 네이티브 앱, App Store 배포 (FFmpeg LGPL 완전 해소)
