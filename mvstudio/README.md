# mvstudio — 로컬 뮤직비디오 생성 엔진 (Phase 0 MVP)

음악 파일 + 이미지 폴더를 넣으면, 곡을 분석해서 **비트에 맞춰 컷이 바뀌는 뮤직비디오**를
전부 로컬에서 렌더링하는 CLI 엔진입니다. 클라우드 호출 없음, 크레딧 없음, 파일이 기기를 떠나지 않습니다.

```
음악.wav + 이미지폴더/
   │
   ├─ ① 오디오 분석 (librosa) ─ BPM, 비트 그리드, 에너지 곡선, 구간 분리
   ├─ ② 이미지 풀 스캔 ──────── 밝기/컬러풀니스 → 분위기 점수 (추후 VLM 대체 지점)
   ├─ ③ 감독(Director) ─────── 스토리보드 JSON 생성
   │     · rule   : 결정적 룰 기반 (기본값, 시드 고정 시 재현 가능)
   │     · ollama : 로컬 LLM(Qwen3 등)이 연출 — 실패 시 rule로 자동 폴백
   ├─ ④ 카메라 프리셋 ───────── presets/camera_presets.json (코드가 아닌 데이터)
   └─ ⑤ 렌더 (FFmpeg) ──────── 컷별 zoompan → concat → 오디오 먹싱 → mp4
```

핵심 설계 원칙: **감독의 출력은 반드시 스토리보드 JSON이고, 렌더러는 그 JSON만 읽는
결정적 엔진**입니다. 감독(모델)을 바꿔도 렌더 품질이 흔들리지 않고, 이후 GUI/MCP 서버가
같은 JSON 위에 그대로 얹힙니다.

## 설치 및 검증 (Mac 기준)

> **먼저 확인**: `python3 --version`이 **3.10 이상**이어야 합니다. macOS 기본
> python3(Xcode CLT의 3.9.6, pip 21.2)는 너무 오래돼 설치가 실패합니다 —
> `brew install python@3.12` 후 아래에서 `python3` 대신 `python3.12`를 쓰세요.

```bash
git clone https://github.com/Huntbae/agency-agents.git
cd agency-agents && git checkout claude/music-video-local-design-41d53y
cd mvstudio
python3.12 -m venv .venv && source .venv/bin/activate   # 3.10+ 인터프리터 사용
python -m pip install --upgrade pip                     # PEP 660 editable 설치에 필요
pip install -e ".[dev,mcp]"
mvstudio doctor                # 환경 점검 + 엔드투엔드 자가 테스트
```

`mvstudio doctor`가 의존성, FFmpeg/인코더, RAM/디스크 티어, Ollama 유무를 점검한 뒤
합성 데모 곡으로 실제 렌더까지 수행해 `RESULT: OK`를 출력하면 설치 검증 완료입니다.
Apple Silicon Mac에서는 인코더가 `h264_videotoolbox`(하드웨어, LGPL-안전)로 잡혀야 정상이며,
`libx264` 경고가 뜨면 GPL 빌드 FFmpeg(예: Homebrew)를 쓰고 있다는 뜻입니다 —
개인 사용은 문제없고, 상용 배포 시에만 LGPL 빌드로 교체하면 됩니다.

FFmpeg는 시스템에 설치된 것을 우선 사용합니다 (`MVSTUDIO_FFMPEG` 환경변수로 지정 가능).
없으면 개발 편의를 위해 `imageio-ffmpeg` 동봉 바이너리로 폴백합니다.

## 사용법

```bash
# 데모 자산 생성 (저작권 없는 합성 곡 + 그라디언트 이미지 6장)
python examples/make_demo_assets.py demo_assets

# 한 방에: 분석 + 스토리보드 + 렌더
mvstudio make demo_assets/demo.wav demo_assets/images -o out.mp4

# 단계별로
mvstudio analyze song.wav -o analysis.json
mvstudio storyboard song.wav images/ -o storyboard.json --seed 42
#   → storyboard.json을 손으로 수정한 뒤
mvstudio render storyboard.json -o out.mp4

# 로컬 LLM 감독 사용 (Ollama 서버 + qwen3 필요; 실패 시 rule 폴백)
mvstudio make song.wav images/ --director ollama --model qwen3:8b -o out.mp4

# 카메라 프리셋 목록
mvstudio presets
```

### 리릭 비디오 모드 (가사 자막)

```bash
# .lrc 가사 파일이 있으면 바로 번인
mvstudio make song.mp3 images/ --lyrics song.lrc -o out.mp4

# 가사 파일이 없으면 로컬 Whisper로 추출 (선택 설치: pip install -e ".[lyrics]")
mvstudio transcribe song.mp3 --language ko     # → song.lrc 생성
mvstudio make song.mp3 images/ --lyrics song.lrc -o out.mp4
```

자막은 Pillow로 투명 PNG에 렌더한 뒤 FFmpeg 코어 `overlay` 필터로 합성합니다 —
drawtext/libass 의존성이 없어 어떤 FFmpeg 빌드에서도 동작합니다. 한글 폰트는
macOS의 AppleSDGothicNeo 등을 자동 감지하며 `MVSTUDIO_FONT`로 지정할 수도 있습니다.

### 컬러 그레이딩·트랜지션 (자동)

구간 에너지에 따라 컬러 그레이드가 자동 적용됩니다(조용한 구간 `cool_muted` →
코러스 `punchy`; `mvstudio/presets_data/color_grades.json`에 데이터로 정의).
구간 경계에는 0.15초 딥 트랜지션이 들어갑니다. 스토리보드 JSON의 컷별
`grade`/`fade_in`/`fade_out` 필드를 수정해 손으로 바꿀 수 있습니다.

## MCP 서버 (Phase 0.5) — Claude가 UI가 되는 경로

엔진을 MCP 도구로 노출합니다. Claude Desktop/Code 등 MCP 클라이언트에서
*"이 폴더의 사진들로 이 곡 뮤직비디오 만들어줘"* 가 한 문장으로 동작합니다.
Higgsfield MCP의 로컬 대응물 — 크레딧 없음, 파일이 기기를 떠나지 않음.

```bash
pip install -e ".[mcp]"       # MCP SDK (MIT) 추가 설치
```

Claude Desktop / Claude Code 설정:

```json
{ "mcpServers": { "mvstudio": { "command": "mvstudio-mcp" } } }
```

제공 도구: `analyze_song`, `list_camera_presets`, `generate_storyboard`,
`inspect_storyboard`, `render_video`, `make_music_video`.
스토리보드 JSON을 에이전트가 수정한 뒤 `render_video`를 다시 부르는 편집 루프를 지원합니다.
(주의: stdio 서버이므로 엔진 로그는 전부 stderr로 나갑니다 — stdout은 JSON-RPC 전용.)

`make`는 최종 mp4 옆에 `*.storyboard.json`을 함께 남기므로, JSON을 수정하고
`mvstudio render`로 다시 뽑는 편집 루프가 MVP에서도 이미 가능합니다.

## 카메라 프리셋

`mvstudio/presets_data/camera_presets.json`에 데이터로 정의됩니다(패키지 데이터로 배포) (T1 = FFmpeg zoompan 기반 2D 모션 12종:
ken burns, zoom, rapid zoom, pan, tilt, push 등). 각 프리셋은 에너지 친화 범위(`energy`)를
선언하고, 감독이 구간 에너지에 맞는 프리셋을 고릅니다. 로드맵의 T2(깊이 패럴랙스 —
Depth Anything V2 **Small**), T3(생성형 — Wan2.2 Fun Camera Control)는 같은 레코드에
계층 필드를 추가하는 방식으로 확장됩니다. 설계 배경은 `docs/DESIGN.md` 참고.

## 라이선스 주의사항 (상용 배포 기준)

이 프로젝트는 상용 클로즈드소스 배포가 가능한 의존성만 사용합니다:
librosa(ISC), soundfile/numpy(BSD), pillow(MIT-CMU), FFmpeg(LGPL 조건부).

- **FFmpeg**: LGPL 빌드만 번들하세요. `--enable-gpl`(libx264/libx265 포함) 빌드 금지 —
  **Homebrew ffmpeg는 GPL 빌드**입니다. macOS에서는 `h264_videotoolbox`가 자동
  선택되며(하드웨어 인코딩, LGPL-안전), 렌더러가 GPL 인코더 사용 시 경고를 출력합니다.
- **오디오 분석**: madmom(모델이 CC BY-NC), Essentia(AGPL), aubio(GPL)는 쓰지 않습니다.
  비트 정확도 개선은 librosa 위 자체 후처리로 해결합니다.
- **모델(옵션 기능)**: Qwen3/Qwen3-VL(Apache-2.0), Wan2.2(Apache-2.0),
  FLUX.2-klein-**4B**(Apache-2.0; 9B는 비상용), Depth Anything V2 **Small**(Apache-2.0;
  Base/Large는 비상용), Whisper(MIT). 사이즈별 라이선스 함정에 주의하세요.

## 테스트

```bash
cd mvstudio && pytest -q     # 합성 곡으로 엔드투엔드 렌더까지 검증 (약 30초)
```

## 로드맵

- Phase 0 (완료): CLI 엔진 코어 + 스토리보드 JSON + T1 프리셋
- Phase 0.5 (완료): 로컬 MCP 서버 (엔진 함수를 MCP 도구로 노출 — Claude가 UI가 됨)
- Phase 2a (완료): 가사 동기화 — LRC 자막 번인 + Whisper 추출(faster-whisper, 선택),
  구간별 컬러 그레이딩, 구간 경계 딥 트랜지션
- Phase 1: 타임라인 GUI (Tauri) + 모델 매니저 (RAM 감지 → 기능 게이팅)
- Phase 2b: Qwen3-VL 이미지 이해, FLUX.2-klein 보충 이미지
- Phase 3: Wan2.2 클립 생성(백그라운드 큐), T2/T3 카메라 프리셋
- Phase 4: SwiftUI + AVFoundation 네이티브 앱 (FFmpeg LGPL 이슈 완전 해소)

전체 설계와 라이선스 검토는 [docs/DESIGN.md](docs/DESIGN.md)에 있습니다.
