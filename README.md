# chatot

강의 녹음(.m4a)을 의학용어가 정확한 녹취록(.md)으로 전사하는 Claude Code 스킬.

## 설치

```bash
git clone https://github.com/kevinpyh48-pixel/chatot ~/.claude/skills/chatot
```

그다음 환경을 한 번 깔아 둔다(uv, mlx-whisper, ffmpeg, pymupdf를 알아서 설치하며, 애플 실리콘 맥 전용).

```bash
bash ~/.claude/skills/chatot/scripts/setup.sh
```

이후 Claude Code에서 "녹음 전사해줘"처럼 말하면 동작한다. 자세한 규칙은 `SKILL.md`와 `references/`에 있다.
