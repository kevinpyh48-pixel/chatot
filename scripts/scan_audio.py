#!/usr/bin/env python3
"""일차 폴더의 음성메모(.m4a 등)를 강의 폴더에 매칭하고 녹취록 유무를 판정한다.

    python3 scan_audio.py "<...>/내분비대사학/2일차"
    python3 scan_audio.py --self-test

day-pipeline 0단계가 이걸 돌려 "전사해야 할 녹음"을 잡는다. 읽기 전용.
매칭이 눈으로는 틀리기 쉬운 이유:
  - 녹음은 강의 폴더 밖(일차 루트)에 있고 파일명에 (교수님)이 없다.
    "뇌하수체 전엽과 시상하부2.m4a"  →  "뇌하수체 전엽과 시상하부(유원상 교수님)/"
  - 분할 녹음(…1.m4a·…2.m4a·_전반부)은 한 강의에 여럿 붙는다 → _녹취록_1.md, _2.md
  - Google Drive 경로는 NFD라 리터럴 비교가 빗나간다 → 전부 NFC로 정규화해 비교
"""
import os
import re
import sys
import unicodedata

# .qta/.mov = 음성메모를 Finder로 내보낼 때 붙기도 하는 QuickTime 컨테이너 확장자.
# 실체는 ISO Media(.m4a와 같은 계열)인데 이 집합에 없어서 285MB짜리 강의 녹음이
# "녹음 없음"으로 지나갈 뻔했다 (2026-08-04, 7일차 「당뇨병의 혈당조절」).
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".caf", ".mp4", ".m4b", ".qta", ".mov"}
SKIP_DIR = {"_구버전", "_변환", "시험지_그림", "족보그림", "_시험대비_모음"}

nfc = lambda s: unicodedata.normalize("NFC", s)


def lecture_key(name):
    """강의명을 매칭용 키로 — (교수님)·분할표시·구분자를 다 떼고 남는 알맹이."""
    s = nfc(name)
    s = re.sub(r"\([^)]*\)", "", s)                       # (유원상 교수님)
    s = re.sub(r"_?(원본|녹음|녹취록|전반부|후반부|앞부분|뒷부분|part)\d*", "", s, flags=re.I)
    s = re.sub(r"[\s_\-–—.]+", "", s)                     # 공백·언더바·하이픈
    s = re.sub(r"\d+$", "", s)                            # 끝 번호(…시상하부2)
    return s.lower()


def match(audio_key, lec_keys):
    """정확일치 → 한쪽이 다른 쪽의 접두 순. 접두 후보가 여럿이면 가장 긴(구체적인) 것."""
    if audio_key in lec_keys:
        return audio_key
    cand = [k for k in lec_keys if k and (k.startswith(audio_key) or audio_key.startswith(k))]
    return max(cand, key=len) if cand else None


def scan(day_dir):
    day_dir = nfc(day_dir).rstrip("/")
    lectures = {}                                          # key -> 강의 폴더명
    for e in sorted(nfc(x) for x in os.listdir(day_dir)):
        if e.startswith("_") or e in SKIP_DIR:
            continue
        if os.path.isdir(os.path.join(day_dir, e)):
            lectures[lecture_key(e)] = e

    audios = []                                            # (강의폴더 or None, 일차기준 상대경로)
    for root, dirs, files in os.walk(day_dir):
        dirs[:] = [d for d in dirs if nfc(d) not in SKIP_DIR]
        for f in sorted(nfc(x) for x in files):
            if f.startswith(".") or os.path.splitext(f)[1].lower() not in AUDIO_EXT:
                continue
            rel = os.path.relpath(nfc(os.path.join(root, f)), day_dir)
            owner = rel.split(os.sep)[0] if os.sep in rel else None   # 강의 폴더 안이면 그게 주인
            if owner not in lectures.values():
                owner = lectures.get(match(lecture_key(os.path.splitext(f)[0]), lectures))
            audios.append((owner, rel))

    rows = []
    for lec in sorted(set(lectures.values())):
        mine = [rel for own, rel in audios if own == lec]
        if not mine:
            continue
        made = sorted(f for f in map(nfc, os.listdir(os.path.join(day_dir, lec)))
                      if ("녹취록" in f or "교수대본" in f) and f.endswith(".md"))
        rows.append((lec, mine, made))
    return rows, [rel for own, rel in audios if own is None]


def main(day_dir):
    rows, orphans = scan(day_dir)
    if not rows and not orphans:
        print("🎵 음성메모 없음 — 녹취록 단계 건너뜀")
        return 0
    todo = 0
    print("| 강의 | 🎵 녹음 | 🎙️ 녹취록 | 할 일 |")
    print("|---|---|---|---|")
    for lec, mine, made in rows:
        # 분할 녹음을 하나로 합친 `<강의>_녹취록.md`는 녹음 개수와 상관없이 완료로 본다
        need = len(mine) > len(made) and not any(f.endswith("_녹취록.md") for f in made)
        todo += 1 if need else 0
        print("| %s | %d개 | %s | %s |" % (
            lec, len(mine), ("%d개" % len(made)) if made else "없음",
            ("chatot 전사 (%s)" % ", ".join(mine)) if need else "✅ 완료"))
    for o in orphans:
        todo += 1
        print("| ❓ 매칭 실패 | %s | – | 어느 강의인지 사용자에게 확인 |" % o)
    print("\n전사 필요: %d건" % todo)
    return 0


def self_test():
    assert lecture_key("뇌하수체 전엽과 시상하부(유원상 교수님)") == lecture_key("뇌하수체 전엽과 시상하부2")
    assert lecture_key("당뇨병의 병인과 진단(김희진 교수님)") == lecture_key("당뇨병의 병인과 진단1")
    assert lecture_key("뇌하수체 후엽(유원상 교수님)") == lecture_key("뇌하수체 후엽(유원상 교수님)_녹음_전반부")
    assert lecture_key("내분비계통 통합강의") != lecture_key("임상내분비학서론")
    # 권장 규약 <강의>_녹음[_N] — 강의록/폴더명과 정확일치로 떨어진다
    assert lecture_key("뇌하수체 후엽_녹음") == lecture_key("뇌하수체 후엽(유원상 교수님)")
    assert lecture_key("뇌하수체 후엽_녹음_2") == lecture_key("뇌하수체 후엽")
    keys = {lecture_key("뇌하수체 전엽과 시상하부(유원상 교수님)"): 1,
            lecture_key("뇌하수체 후엽(유원상 교수님)"): 1}
    assert match(lecture_key("뇌하수체 전엽과 시상하부3"), keys) == lecture_key("뇌하수체 전엽과 시상하부(유원상 교수님)")
    assert match(lecture_key("뇌하수체 후엽"), keys) == lecture_key("뇌하수체 후엽(유원상 교수님)")
    assert match(lecture_key("전혀다른강의"), keys) is None
    # NFD로 들어와도 같은 키 — Google Drive 경로가 이 형태다
    assert lecture_key(unicodedata.normalize("NFD", "뇌하수체 후엽")) == lecture_key("뇌하수체 후엽")
    print("self-test ok")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(self_test() if a[:1] == ["--self-test"] else
             main(a[0]) if a else (print(__doc__) or 2))
