#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_ledger.py —— 把历史稿件目录导入选题台账

用法:
    python3 import_ledger.py <稿件目录> [--ledger ledger.csv] [--glob "*.md"] [--days 7]

日期来源优先级：文件名里的 YYYY-MM-DD > 文件内首个日期 > 文件修改时间。
每个二级标题（##）作为一条选题记录；没有二级标题时取一级标题。
重复运行会按 (date, title) 去重，不会写重。
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def extract_date(path, text):
    m = DATE_RE.search(path.name)
    if m:
        return m.group(1)
    m = DATE_RE.search(text[:500])
    if m:
        return m.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def extract_titles(text):
    titles = []
    for ln in text.splitlines():
        m = re.match(r"^\s{0,3}#{2}\s+(?!\d+\.\s*$)(.+?)\s*$", ln)
        if m:
            t = re.sub(r"[*_`]", "", m.group(1)).strip()
            if t and not DATE_RE.fullmatch(t):
                titles.append(t)
    if not titles:
        for ln in text.splitlines():
            m = re.match(r"^\s{0,3}#{1}\s+(.+?)\s*$", ln)
            if m:
                titles.append(m.group(1).strip())
                break
    return titles


def main():
    ap = argparse.ArgumentParser(description="导入历史稿件到选题台账")
    ap.add_argument("source", help="稿件目录")
    ap.add_argument("--ledger", default=str(Path(__file__).resolve().parent / "ledger.csv"))
    ap.add_argument("--glob", default="*.md", help="匹配模式，默认 *.md")
    ap.add_argument("--days", type=int, default=0, help="只导入最近N天（0=全部）")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.is_dir():
        print("[错误] 不是目录：%s" % src, file=sys.stderr)
        return 2

    lp = Path(args.ledger)
    existing = set()
    if lp.exists():
        with open(lp, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                existing.add((row.get("date", ""), row.get("title", "")))

    cutoff = None
    if args.days:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=args.days)

    added = 0
    rows = []
    for p in sorted(src.glob(args.glob)):
        text = p.read_text(encoding="utf-8", errors="replace")
        d = extract_date(p, text)
        if cutoff:
            try:
                if datetime.strptime(d, "%Y-%m-%d") < cutoff:
                    continue
            except ValueError:
                pass
        for title in extract_titles(text):
            key = (d, title)
            if key in existing:
                continue
            existing.add(key)
            rows.append([d, title, "", ""])
            added += 1

    lp.parent.mkdir(parents=True, exist_ok=True)
    new = not lp.exists() or lp.stat().st_size == 0
    with open(lp, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "title", "keywords", "register"])
        w.writerows(rows)

    print("导入 %d 条选题 -> %s" % (added, lp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
