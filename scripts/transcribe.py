#!/usr/bin/env python3
"""chatot 전사 파이프라인: .m4a → 타임스탬프 세그먼트 텍스트.

이 맥 제약(ffmpeg·brew 없음, 시스템 파이썬 쓰기 금지) 우회:
afconvert(내장)로 디코딩 → uv venv의 mlx-whisper에 numpy 배열 직접 전달.

이 스크립트는 venv의 파이썬으로 실행해야 한다. venv가 없으면:
  uv venv --python 3.11 ~/.cache/chatot/.venv
  uv pip install --python ~/.cache/chatot/.venv/bin/python mlx-whisper soundfile
실행:
  ~/.cache/chatot/.venv/bin/python transcribe.py 입력.m4a --glossary 용어집.txt \
      --out 출력_raw.md [--limit-seconds 60]
"""
import argparse
import os
import shutil
import subprocess
import tempfile

MODEL = "mlx-community/whisper-large-v3-turbo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help=".m4a/.wav 입력")
    ap.add_argument("--glossary", help="의학용어 목록 파일(한 줄 1용어) → initial_prompt")
    ap.add_argument("--out", required=True, help="출력 md 경로")
    ap.add_argument("--no-norm", action="store_true", help="음량 정규화 끄기(ffmpeg 경로만 해당)")
    ap.add_argument("--limit-seconds", type=int, help="앞부분만 전사(스모크 테스트용)")
    args = ap.parse_args()

    import soundfile
    import mlx_whisper

    if args.audio.lower().endswith(".wav"):
        wav = args.audio
    else:
        wav = os.path.join(tempfile.mkdtemp(), "audio.wav")
        ffmpeg = shutil.which("ffmpeg") or os.path.expanduser("~/.local/bin/ffmpeg")
        if os.path.exists(ffmpeg):
            # 원거리 녹음(평균 -37dB)은 정규화 없이는 whisper가 음차를 깨뜨린다(탈구→탈부, 사지→사진).
            # afconvert는 드라이브 한글 경로에서 멈추기도 해서 ffmpeg를 우선한다.
            af = [] if args.no_norm else ["-af", "highpass=f=80,dynaudnorm=f=150:g=15,loudnorm=I=-20"]
            subprocess.run([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-i", args.audio,
                            *af, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], check=True)
        else:
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", args.audio, wav],
                check=True,
            )

    audio, sr = soundfile.read(wav, dtype="float32")
    assert sr == 16000, f"샘플레이트 {sr} != 16000"
    if args.limit_seconds:
        audio = audio[: sr * args.limit_seconds]

    initial_prompt = None
    if args.glossary:
        with open(args.glossary, encoding="utf-8") as f:
            prompt_text = f.read().strip()
        # whisper initial_prompt는 마지막 224토큰만 반영된다. 용어 나열보다
        # "원하는 출력 문체 샘플"(한국어 문장 + 영문 용어)이 훨씬 잘 먹힌다.
        initial_prompt = prompt_text

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        language="ko",
        initial_prompt=initial_prompt,
        condition_on_previous_text=False,  # 무음 구간 반복 환각 억제
    )

    with open(args.out, "w", encoding="utf-8") as f:
        for seg in result["segments"]:
            m, s = divmod(int(seg["start"]), 60)
            f.write(f"[{m:02d}:{s:02d}] {seg['text'].strip()}\n")
    print(f"완료: {args.out} ({len(result['segments'])} 세그먼트)")


if __name__ == "__main__":
    main()
