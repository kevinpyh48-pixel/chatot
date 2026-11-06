#!/bin/bash
# chatot 환경 준비. 여러 번 돌려도 안전하다(이미 있는 건 건너뜀).
# 깔리는 것: uv, 파이썬 3.11 venv(~/.cache/chatot/.venv), mlx-whisper, soundfile, pymupdf, ffmpeg
set -e

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "✗ 애플 실리콘(M1 이상) 맥에서만 동작한다 (mlx-whisper 제약)."; exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
VENV="$HOME/.cache/chatot/.venv"
PY="$VENV/bin/python"

# 1) uv
if ! command -v uv >/dev/null; then
  echo "→ uv 설치"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2) venv + 파이썬 패키지
[ -x "$PY" ] || { echo "→ venv 생성"; uv venv --python 3.11 "$VENV"; }
echo "→ 패키지 확인/설치"
uv pip install --python "$PY" -q mlx-whisper soundfile pymupdf imageio-ffmpeg

# 3) ffmpeg (없으면 imageio-ffmpeg가 들고 있는 바이너리를 ~/.local/bin에 연결)
if ! command -v ffmpeg >/dev/null; then
  FF="$("$PY" -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
  mkdir -p "$HOME/.local/bin"
  ln -sf "$FF" "$HOME/.local/bin/ffmpeg"
  echo "→ ffmpeg 연결: ~/.local/bin/ffmpeg"
fi

# 4) 확인
"$PY" -c "import mlx_whisper, soundfile, pymupdf; print('✓ python 패키지 OK')"
ffmpeg -version 2>/dev/null | head -1 || "$HOME/.local/bin/ffmpeg" -version | head -1
echo "✓ 준비 끝. (첫 전사 때 whisper 모델 ~1.6GB가 자동 다운로드된다)"
