#!/usr/bin/env python3
"""녹취록(교수 대본) 형식 정리: 시각·볼 슬라이드·핵심 내용 제거 + 정리본 절 체계 목차.

usage:
  python3 -I format_transcript.py <과목폴더 또는 녹취록.md>... [--apply] [--out DIR]

- 기본은 dry-run(검사 리포트만). --apply 면 원본을 <일차>/_구버전/<YYMMDD>/ 로 복사한 뒤 덮어쓴다.
- --out DIR 이면 결과를 DIR 에 쓰고 원본은 건드리지 않는다(눈으로 확인용).
- 멱등: 머리말에 「형식 변경(」 표시가 있으면 건너뛴다. _raw 파일은 건드리지 않는다.
- 같은 폴더에 _정리본.md 가 있고 절 제목에 쪽 범위가 있으면 정리본 절(§) 아래로 묶고(group 모드),
  없으면 섹션 순서 그대로 링크 목차만 만든다(flat 모드).
- 드라이브 한글 경로는 NFD 라 이름은 NFC 로 정규화해서 비교한다.
"""
import datetime
import os
import re
import shutil
import sys
import unicodedata

NFC = lambda s: unicodedata.normalize("NFC", s)
STAMP = datetime.date.today().strftime("%y%m%d")
MARK = "형식 변경("

TS_BR = re.compile(r"\[(?:\d교시 )?\d{1,2}:\d{2}(?:~(?:\d교시 )?\d{1,2}:\d{2})?(?: ([^\]]+))?\]\s?")
TAIL_RE = re.compile(r"^(?:⚠️\s*)?(교정 로그|환각|컷한 환각|자른 구간|잘라낸 구간|불명확 구간|확인 요망|불확실|못 옮긴|시험 범위 발언 판정)")
TOPMETA_RE = re.compile(r"(출제 예고 요약|출제 신호 요약)")
PAGE_RE = re.compile(r"(?:p\.?|슬라이드)\s*(\d+)")


def strip_ts(text):
    text = TS_BR.sub(lambda m: f"({m.group(1)}) " if m.group(1) else "", text)
    text = re.sub(r"\s*,?\s*`\d{1,2}:\d{2}(?:~\d{1,2}:\d{2})?`", "", text)
    text = re.sub(r"\(\s*~?\d{1,2}:\d{2}(?:~\d{1,2}:\d{2})?~?\s*\)", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).rstrip()


def clean_heading(raw):
    """제목에서 시각 제거 + 쪽 표기 통일 + 옵시디언 링크 금지 문자 정리."""
    h = raw[3:].strip()
    h = re.sub(r"\s*`[^`]*\d{1,2}:\d{2}[^`]*`", "", h)
    h = re.sub(r"\s*\([^()]*\d{1,2}:\d{2}[^()]*\)", "", h)
    h = re.sub(r"\((?:p\.?|슬라이드)\s*[^)]*\)", lambda m: m.group(0).replace("슬라이드 ", "p").replace("p. ", "p").replace("p.", "p").replace("–", "~"), h)
    h = re.sub(r":\s+", " — ", h)
    h = h.replace(":", "：")
    h = h.replace("|", "·")
    h = re.sub(r"[#^\[\]]", "", h)
    return re.sub(r"\s{2,}", " ", h).strip()


def first_page(raw):
    m = PAGE_RE.search(raw)
    return int(m.group(1)) if m else None


def parse_groups(path):
    """정리본 '## N. 제목 (pA~B · pC)' → [(heading, [(a,b),...])]"""
    groups = []
    for l in open(path, encoding="utf-8").read().split("\n"):
        if not l.startswith("## ") or "⚠️" in l[:6]:
            continue
        m = re.search(r"\(((?:p\.?\s*\d+(?:~\d+)?[ ·,]*)+)\)\s*$", l)
        if not m:
            continue
        rngs = [(int(a), int(b or a)) for a, b in re.findall(r"p\.?\s*(\d+)(?:~(\d+))?", m.group(1))]
        groups.append((l[3:].strip(), rngs))
    return groups


def map_page(p, groups):
    best, bd = 0, 10**9
    for gi, (_, rngs) in enumerate(groups):
        for a, b in rngs:
            if a <= p <= b:
                return gi
            d = min(abs(p - a), abs(p - b))
            if d < bd:
                best, bd = gi, d
    return best


def smooth(seq):
    """None 채우기 → 낀 이상치(길이≤2) 흡수 → 단조 증가 강제. (결과, 강제 횟수)"""
    n = len(seq)
    for i in range(n):
        if seq[i] is None:
            seq[i] = seq[i - 1] if i and seq[i - 1] is not None else None
    for i in range(n - 1, -1, -1):
        if seq[i] is None:
            seq[i] = seq[i + 1] if i + 1 < n else 0
    # 최장 비감소 부분수열은 그대로 두고, 어긋난 섹션만 앞쪽(없으면 뒤쪽) 유지 항목의 절에 붙인다
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] <= seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(n), key=lambda i: best[i]) if n else -1
    keep = set()
    while end != -1:
        keep.add(end)
        end = prev[end]
    out, last = list(seq), None
    first_keep = min(keep) if keep else 0
    for i in range(n):
        if i in keep:
            last = seq[i]
        else:
            out[i] = last if last is not None else seq[first_keep]
    return out, n - len(keep)


def drop_time_column(lines):
    """표 머리에 '시각' 열이 있으면 그 열을 뺀다."""
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            hdr = [c.strip() for c in l.strip().strip("|").split("|")]
            tbl = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl.append(lines[i])
                i += 1
            if "시각" in hdr:
                k = hdr.index("시각")
                for r in tbl:
                    cells = r.strip().strip("|").split("|")
                    if len(cells) > k:
                        del cells[k]
                    out.append("|" + "|".join(cells) + "|")
            else:
                out += tbl
            continue
        out.append(l)
        i += 1
    return out


def convert(path, group_src):
    lines = open(path, encoding="utf-8").read().split("\n")
    if any(MARK in l for l in lines[:12]):
        return None, {"skip": "이미 변환됨"}
    h2 = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if len(h2) < 3:
        return None, {"skip": "H2 섹션 3개 미만"}
    intro = lines[: h2[0]]
    while intro and not intro[-1].strip():
        intro.pop()
    # 구간 분리
    secs = []
    for a, b in zip(h2, h2[1:] + [len(lines)]):
        secs.append((lines[a], lines[a + 1 : b]))
    tail_i = next((i for i, (h, _) in enumerate(secs) if TAIL_RE.match(h[3:].strip())), len(secs))
    tail = secs[tail_i:]
    body = secs[:tail_i]
    bad = [h for h, _ in tail if not TAIL_RE.match(h[3:].strip()) and not TOPMETA_RE.search(h)]
    topmeta, real = [], []
    for h, b in body:
        t = h[3:].strip()
        if t.startswith("목차"):
            continue
        (topmeta if TOPMETA_RE.search(t) else real).append((h, b))
    info = {"bad_after_tail": bad}
    # 섹션 본문
    stats = {"slide": 0, "core": 0, "ts": 0}
    period, out_secs = None, []
    for h, b in real:
        mh = re.search(r"\((\d)교시 \[\d", h)
        o, in_core = [], False
        if mh and mh.group(1) != period:
            period = mh.group(1)
            o += [f"**━━ {period}교시 ━━**", ""]
        for l in b:
            if l.startswith("**볼 슬라이드**"):
                stats["slide"] += 1
                continue
            if l.startswith("### 핵심 내용"):
                in_core = True
                continue
            if l.startswith("### 교수 대본"):
                in_core = False
                continue
            if in_core:
                stats["core"] += 1
                continue
            if l.strip() == "---":
                continue
            m = re.match(r"^(?:[-🎙️🔥⭐ ]*)\[(\d)교시 \d", l)
            if m and m.group(1) != period:
                period = m.group(1)
                o += [f"**━━ {period}교시 ━━**", ""]
            stats["ts"] += len(TS_BR.findall(l))
            s = strip_ts(l)
            if re.fullmatch(r"\s*[-*]\s*", s):
                continue
            o.append(s)
        o = drop_time_column(o)
        while o and not o[-1].strip():
            o.pop()
        while o and not o[0].strip():
            o.pop(0)
        out_secs.append((clean_heading(h), first_page(h), o))
    # 머리말·상단 메타
    intro = [strip_ts(l) for l in intro]
    topmeta = [(clean_heading(h), drop_time_column([strip_ts(x) for x in b])) for h, b in topmeta]
    note = "> ✂️ 형식 변경(" + datetime.date.today().isoformat() + "): 문장별 시각 `[mm:ss]`·「볼 슬라이드」·「핵심 내용」을 뺐다. 전사문과 교시 구분만 남김. 이전 판은 `_구버전/" + STAMP + "/`."
    # 모드 결정
    groups = parse_groups(group_src) if group_src else []
    pages = [p for _, p, _ in out_secs]
    have = sum(p is not None for p in pages)
    mode = "group" if groups and out_secs and have / len(out_secs) >= 0.5 else "flat"
    if mode == "group":
        seq = [map_page(p, groups) if p is not None else None for p in pages]
        seq, forced = smooth(seq)
        info["forced"] = forced
        if forced / len(out_secs) > 0.3:  # 정리본 절과 쪽 순서가 너무 어긋나면 묶지 않는다
            mode, info["fallback"] = "flat", f"어긋남 {forced}/{len(out_secs)}"
    if mode == "group":  # 정리본 절 번호와 겹치지 않게 섹션 제목의 'N.' 번호는 뗀다
        out_secs = [(re.sub(r"^\d+\.\s+", "", t), p, o) for t, p, o in out_secs]
    seen = {}
    for k, (t, p, o) in enumerate(out_secs):  # 제목 중복 해소
        seen[t] = seen.get(t, 0) + 1
        if seen[t] > 1:
            out_secs[k] = (f"{t} ({seen[t]})", p, o)
    res = intro + [note, ""]
    toc = ["## 목차", ""]
    if mode == "group":
        toc += ["> 정리본의 절과 같은 이름·쪽 범위. 본문은 녹음 순서라 슬라이드 순서와 어긋나는 곳이 있다.", ""]
        order = []
        for g in seq:
            if g not in order:
                order.append(g)
        for g in order:
            gt = groups[g][0]
            short = re.sub(r"\s*\(p[^)]*\)\s*$", "", gt)
            rng = re.search(r"\((p[^)]*)\)\s*$", gt).group(1)
            toc.append(f"**[[#{gt}|{short}]]** `{rng}`  ")
            for (t, _, _), gg in zip(out_secs, seq):
                if gg == g:
                    toc.append(f"　[[#{t}|{t}]]  ")
            toc.append("")
        info["groups"] = len(order)
    else:
        for t, _, _ in out_secs:
            toc.append(f"- [[#{t}|{t}]]")
        toc.append("")
    res += toc
    for t, b in topmeta:
        res += ["", f"## {t}", ""] + b
    res += ["", "---", ""]
    if mode == "group":
        cur = None
        for (t, _, o), g in zip(out_secs, seq):
            if g != cur:
                res += [f"## {groups[g][0]}", ""]
                cur = g
            body_lines = [("#" + l if re.match(r"^#{3,5} ", l) else l) for l in o]
            res += [f"### {t}", ""] + body_lines + [""]
    else:
        for t, _, o in out_secs:
            res += [f"## {t}", ""] + o + [""]
    if tail:
        res += ["---", "", "> 아래 로그의 `[mm:ss]`는 시각 표기를 뺀 이 판이 아니라 `_구버전/" + STAMP + "/`의 이전 판 기준이다.", ""]
        for h, b in tail:
            res += [h] + b
    text = "\n".join(res).rstrip("\n") + "\n"
    body_text = text.split("\n---\n\n> 아래 로그")[0]
    info.update(mode=mode, sections=len(out_secs), stats=stats,
                left_ts=len(re.findall(r"\[(?:\d교시 )?\d{1,2}:\d{2}", body_text)),
                page_cover=f"{have}/{len(out_secs)}")
    return text, info


def find_summary(d):
    for f in os.listdir(d):
        if NFC(f).endswith("_정리본.md"):
            return os.path.join(d, f)
    return None


def collect(args):
    out = []
    for a in args:
        if os.path.isfile(a):
            out.append(a)
            continue
        for r, ds, fs in os.walk(a):
            ds[:] = [d for d in ds if "_구버전" not in NFC(d) and "_artifacts" not in NFC(d)]
            for f in fs:
                nf = NFC(f)
                if "녹취록" in nf and nf.endswith(".md") and "_raw" not in nf:
                    out.append(os.path.join(r, f))
    return sorted(out)


def main():
    argv = sys.argv[1:]
    apply = "--apply" in argv
    outdir = None
    if "--out" in argv:
        outdir = argv[argv.index("--out") + 1]
    paths = [a for a in argv if not a.startswith("--") and a != outdir]
    for p in collect(paths):
        d = os.path.dirname(p)
        text, info = convert(p, find_summary(d))
        name = NFC(os.path.basename(p))
        if text is None:
            print(f"SKIP  {name[:50]:50} {info['skip']}")
            continue
        flag = "OK  " if info["left_ts"] == 0 and not info["bad_after_tail"] else "WARN"
        print(f"{flag}  {name[:50]:50} {info['mode']:5} 섹션{info['sections']:3} 쪽{info['page_cover']:6} 시각-{info['stats']['ts']:4}"
              f" 볼슬-{info['stats']['slide']:2} 핵심줄-{info['stats']['core']:3} 잔여시각{info['left_ts']} 강제{info.get('forced', 0)} 그룹{info.get('groups', '-')}"
              + (f" 꼬리뒤섹션={info['bad_after_tail']}" if info["bad_after_tail"] else ""))
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            open(os.path.join(outdir, name), "w", encoding="utf-8").write(text)
        elif apply and flag == "OK  ":
            day = os.path.dirname(d)
            arc = os.path.join(day, "_구버전", STAMP)
            os.makedirs(arc, exist_ok=True)
            dst = os.path.join(arc, os.path.basename(p))
            if os.path.exists(dst):
                print(f"      ↳ 보관본이 이미 있어 건너뜀: {dst}")
                continue
            shutil.copy2(p, dst)
            open(p, "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    main()
