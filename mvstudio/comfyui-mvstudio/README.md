# comfyui-mvstudio — 뮤직비디오 엔진 ComfyUI 노드

mvstudio 엔진(곡 분석 → 비트싱크 스토리보드 → 렌더)을 ComfyUI 노드로 노출하고,
ComfyUI의 **립싱크 노드들과 연결**해 "업로드한 사진이 노래를 따라 부르는" 뮤직비디오를
만듭니다. 노드 간에는 파일 경로(STRING)를 주고받으므로 어떤 노드 팩과도 조합됩니다.

## 설치

```bash
# ComfyUI가 ~/ComfyUI에 있다고 가정
ln -s ~/agency-agents/mvstudio/comfyui-mvstudio ~/ComfyUI/custom_nodes/comfyui-mvstudio
# mvstudio 의존성은 ComfyUI의 파이썬에 한 번만:
~/ComfyUI/.venv/bin/pip install librosa soundfile numpy pillow imageio-ffmpeg
```

재시작하면 `mvstudio` 카테고리에 노드 5개가 나타납니다.

## 노드

| 노드 | 입력 → 출력 |
|---|---|
| **MVStudio: Analyze Song** | 곡 경로 → 분석 JSON + 구간 요약 (몇 번 구간이 코러스인지 확인) |
| **MVStudio: Storyboard** | 곡 (+사진 폴더 또는 가사) → 스토리보드 JSON 경로 |
| **MVStudio: Section Audio** | 곡+스토리보드+구간번호 → 그 구간의 오디오(wav) — **립싱크 노드에 먹일 입력** |
| **MVStudio: Place Clip** | 스토리보드+비디오 → 립싱크 클립을 해당 구간에 연속 합성 |
| **MVStudio: Render** | 스토리보드 → 최종 mp4 |

## 립싱크 뮤직비디오 워크플로 (사진이 노래를 부르는 코러스)

```
[곡.mp3] ─┬─> MVStudio: Storyboard ──────────────┬─> MVStudio: Place Clip ─> MVStudio: Render ─> 최종.mp4
          │      (sections_summary에서             │        ▲
          │       코러스 구간 번호 확인)            │        │ (립싱크 mp4 경로)
          └─> MVStudio: Section Audio (코러스 구간)│   [Save Video (VHS)]
                        │                          │        ▲
                        ▼                          │        │
              [립싱크 노드: 인물사진 + 구간오디오] ──────────┘
               (LatentSync / Sonic / SadTalker)
```

순서: ① Storyboard 실행 → 구간 요약에서 코러스(high) 번호 확인 → ② Section Audio로
그 구간의 노래 오디오 추출 → ③ 립싱크 노드에 **인물 사진 + 그 오디오**를 넣어 말하는
얼굴 클립 생성 → ④ Save Video로 mp4 저장 → ⑤ 그 경로를 Place Clip에 → ⑥ Render.
결과: 벌스에서는 사진들이 비트 컷으로 흐르다가, 코러스에서 인물이 립싱크로 노래합니다.

## 맥(Apple Silicon)용 립싱크 노드 선택 가이드

Apple Silicon에서 실사용 보고가 있는 조합 ([ComfyUI 포럼 Mac 립싱크 스레드](https://forum.comfy.org/t/lip-sync-workflow-for-mac-apple-silicon/3919) 참고):

| 도구 | 노드 | 라이선스 | 비고 |
|---|---|---|---|
| **LatentSync** (ByteDance) | [ComfyUI-LatentSyncWrapper](https://github.com/ShmuelRonen/ComfyUI-LatentSyncWrapper) | Apache-2.0 ✅ | 립 정확도 높음. 입력이 *영상* 기준이라 사진은 짧은 루프 영상으로 만들어 사용 |
| **Sonic** (Tencent) | ComfyUI_Sonic | 비상업 연구용 ⚠️ | 사진 1장→말하는 얼굴. 개인 사용 OK, 상용 배포 불가 |
| **SadTalker** | ComfyUI-SadTalker | Apache-2.0 ✅ | 가볍고 맥에서 잘 돌지만 품질은 구세대 |

개인 사용 권장: **Sonic**(사진 1장으로 가장 간단) 또는 **LatentSync**(품질 우선).
상용 배포까지 고려하면 LatentSync/SadTalker(Apache)만 사용하세요.
주의: 이 모델들은 CUDA 우선으로 개발되어 맥에서는 느립니다(수 초 클립에 수 분).
립싱크는 코러스 한 구간에만 쓰는 것이 시간·품질 모두 현실적입니다.

## ComfyUI 없이 (CLI만으로)

립싱크 클립을 어떤 도구로든 만들었다면 ComfyUI 없이도 합성됩니다:

```bash
mvstudio storyboard song.mp3 photos/ -o sb.json
mvstudio section-audio song.mp3 sb.json --section 2 -o chorus.wav
# → chorus.wav + 인물사진으로 립싱크 도구 실행 → talking.mp4
mvstudio place-clip sb.json talking.mp4 --section 2
mvstudio render sb.json -o final.mp4
```
