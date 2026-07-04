#!/bin/bash
# mvstudio 맥 설치/업데이트 스크립트.
# 몇 번을 다시 실행해도 안전합니다(멱등). 사용법:
#   bash ~/agency-agents/mvstudio/setup-mac.sh
# 완료 후에는 어떤 터미널에서든 venv 활성화 없이 `mvstudio ...`가 동작합니다.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "==> 1/5 코드 업데이트 (git pull)"
git pull --ff-only 2>/dev/null || \
  echo "    (pull 생략 — 오프라인이거나 로컬 변경이 있습니다. 계속 진행)"

echo "==> 2/5 Python 3.10+ 찾기"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "    Python 3.10 이상이 없습니다. 먼저 실행하세요:  brew install python@3.12"
  exit 1
fi
echo "    사용: $("$PY" --version) ($PY)"

echo "==> 3/5 가상환경 준비 (.venv)"
if [ ! -x .venv/bin/python ] || \
   ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  rm -rf .venv
  "$PY" -m venv .venv
  echo "    새로 생성"
else
  echo "    기존 재사용"
fi
.venv/bin/python -m pip install --quiet --upgrade pip

echo "==> 4/5 mvstudio 설치 (가사·HEIC·MCP·이미지생성 포함 — 몇 분 걸릴 수 있음)"
if ! .venv/bin/pip install --quiet -e ".[dev,mcp,lyrics,heic,gen]"; then
  echo "    경고: 이미지 생성(mflux) 포함 설치 실패 — 원인을 표시합니다:"
  .venv/bin/pip install -e ".[dev,mcp,lyrics,heic,gen]" 2>&1 | tail -15 || true
  echo "    이미지 생성 제외하고 계속 설치합니다 (--visuals generate 사용 불가)"
  .venv/bin/pip install --quiet -e ".[dev,mcp,lyrics,heic]"
fi

echo "==> 5/5 mvstudio 명령어 전역 등록"
BIN=""
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
  if [ -d "$d" ] && [ -w "$d" ]; then BIN="$d"; break; fi
done
if [ -z "$BIN" ]; then BIN="$HOME/.local/bin"; mkdir -p "$BIN"; fi
ln -sf "$REPO_DIR/.venv/bin/mvstudio" "$BIN/mvstudio"
ln -sf "$REPO_DIR/.venv/bin/mvstudio-mcp" "$BIN/mvstudio-mcp"
echo "    등록됨: $BIN/mvstudio (새 터미널에서도 venv 활성화 없이 바로 사용)"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "    주의: $BIN 이 PATH에 없습니다. 이 줄을 실행하세요:"
     echo "         echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
esac

echo
"$REPO_DIR/.venv/bin/mvstudio" doctor
