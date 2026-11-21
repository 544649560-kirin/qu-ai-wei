#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight.py —— 发布前闸门（命令行版）

用法:
    python3 preflight.py 稿件.md                    # 通用配置
    python3 preflight.py 稿件.md --profile 公众号    # 场景包
    python3 preflight.py 稿件.md --ai               # 额外跑 DeepSeek 终审
    python3 preflight.py 稿件.md --register 经史笔记 # 指定语域

退出码: 0 放行 / 1 拦截 / 2 参数或文件错误

规则全部来自同目录 rules.json；改检查项不要动本文件。
"""
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ---------- 基础工具 ----------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() in (".html", ".htm"):
        m = re.search(r"<body[^>]*>(.*?)</body>", raw, re.S | re.I)
        body = m.group(1) if m else raw
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
        body = re.sub(r"<br\s*/?>|</p>|</div>|</h[1-6]>", "\n", body, flags=re.I)
        body = re.sub(r"<[^>]+>", " ", body)
        return html_mod.unescape(body)
    return raw


def norm_line(ln):
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", ln)
    s = re.sub(r"^\s{0,3}>\s*", "", s)
    s = re.sub(r"[*_`]", "", s)
    return s.strip()


def is_exempt(line, markers):
    return any(m in line for m in markers)


def bigrams(s):
    s = re.sub(r"[\s，。、；：！？「」『』（）()《》,.;:!?…—\-\d]+", "", s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def get_title(text, path):
    for ln in text.splitlines():
        s = norm_line(ln)
        if not s:
            continue
        if s.startswith("# "):
            return s[2:].strip()
        if len(s) < 80 and not s.startswith("```"):
            return s
    return Path(path).stem


def get_keywords(text, limit=8):
    counts = {}
    for seg in re.findall(r"[\u4e00-\u9fa5]{2,8}", text):
        counts[seg] = counts.get(seg, 0) + 1
    out = []
    for w, c in sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        if c < 3:
            break
        if any(w in x or x in w for x in out):
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


# ---------- 规则解析（兼容 v1 / v2） ----------

def resolve_profile(cfg, name):
    """v2: 返回合并后的配置字典；v1: 直接返回原 cfg。"""
    if "profiles" not in cfg:
        return cfg
    profiles = cfg["profiles"]
    default = cfg.get("default_profile", "通用")
    name = name or default
    if name not in profiles:
        print("[警告] 未知场景包 %s，使用 %s。可用：%s" %
              (name, default, "、".join(profiles)), file=sys.stderr)
        name = default
    p = profiles[name]
    base = cfg.get("base", {})
    return {
        "_profile": name,
        "_label": p.get("label", name),
        "hard_terms": p.get("hard_terms", []),
        "ai_taste_phrases": base.get("ai_taste_phrases", []) if p.get("use_base") else [],
        "regex_groups": base.get("regex_groups", []) if p.get("use_base") else [],
        "exempt_markers": base.get("exempt_markers", []),
        "register_profiles": p.get("register_profiles"),
        "register_min_hits": p.get("register_min_hits", 3),
        "dedup": cfg.get("dedup", {}),
        "ai_review": cfg.get("ai_review", {}),
    }


# ---------- 台账 ----------

def load_ledger(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_ledger(path, title, keywords, register):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists() or p.stat().st_size == 0
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "title", "keywords", "register"])
        w.writerow([datetime.now().strftime("%Y-%m-%d"), title, " ".join(keywords), register or ""])


def check_dedup(title, keywords, ledger, cfg):
    if not cfg.get("enabled", True):
        return []
    days = int(cfg.get("window_days", 7))
    threshold = float(cfg.get("threshold", 0.55))
    cutoff = datetime.now() - timedelta(days=days)
    target = bigrams(title + " " + " ".join(keywords))
    hits = []
    for row in ledger:
        try:
            d = datetime.strptime(row.get("date", ""), "%Y-%m-%d")
        except ValueError:
            continue
        if d < cutoff:
            continue
        score = jaccard(target, bigrams(row.get("title", "") + " " + row.get("keywords", "")))
        if score >= threshold:
            hits.append((round(score, 2), row.get("date", ""), row.get("title", "")))
    hits.sort(reverse=True)
    return hits


# ---------- 各项检查 ----------

def check_terms(lines, terms, exempt, label):
    hits = []
    for i, raw in enumerate(lines, 1):
        ln = norm_line(raw)
        if not ln or is_exempt(ln, exempt):
            continue
        for w in terms:
            if w in ln:
                hits.append((i, label, w, ln[:40]))
    return hits


def check_regex(lines, patterns, exempt):
    hits = []
    for i, raw in enumerate(lines, 1):
        ln = norm_line(raw)
        if not ln or is_exempt(ln, exempt):
            continue
        for item in patterns:
            for m in re.finditer(item["regex"], ln):
                hits.append((i, item["name"], m.group(0).strip()[:30], ln[:40]))
    return hits


def check_register(lines, profiles, min_hits, forced):
    if not profiles:
        return None, {}
    text = "\n".join(norm_line(x) for x in lines)
    counts = {name: sum(text.count(w) for w in words) for name, words in profiles.items()}
    if forced and forced in profiles:
        main = forced
    else:
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        if not ranked or ranked[0][1] < min_hits:
            return None, counts
        main = ranked[0][0]
    foreign = {k: v for k, v in counts.items() if k != main and v >= 2}
    return (main, foreign) if foreign else None, counts


# ---------- DeepSeek 终审 ----------

def deepseek_review(text, cfg):
    key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "").strip()
    if not key:
        for fp in cfg.get("api_key_files", []):
            p = Path(fp).expanduser()
            if p.exists():
                key = p.read_text(encoding="utf-8").strip().splitlines()[-1].strip()
                if key:
                    break
    if not key:
        return None, "未找到 API key：请设置环境变量 DEEPSEEK_API_KEY 或写入本地密钥文件"
    try:
        import requests
    except ImportError:
        return None, "缺少 requests，先 pip3 install requests"
    payload = {
        "model": cfg.get("model", "deepseek-v4-pro"),
        "messages": [
            {"role": "system", "content": cfg["system_prompt"]},
            {"role": "user", "content": cfg["user_prompt_template"].format(article=text)},
        ],
        "max_tokens": 4000, "temperature": 0.3, "stream": False,
    }
    try:
        r = requests.post(cfg.get("endpoint", "https://api.deepseek.com/chat/completions"),
                          headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                          json=payload, timeout=300)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], None
        return None, "API 错误 %s: %s" % (r.status_code, r.text[:300])
    except Exception as e:
        return None, "请求失败: %s" % e


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="发布前闸门：选题去重 + 合规词 + AI味 + 语域一致性")
    ap.add_argument("article", help="稿件路径（md / txt / html）")
    ap.add_argument("--rules", default=str(HERE / "rules.json"))
    ap.add_argument("--ledger", default=str(HERE / "ledger.csv"))
    ap.add_argument("--profile", default="", help="场景包：通用 / 公众号 / 财经房产")
    ap.add_argument("--ai", action="store_true", help="额外跑 DeepSeek 终审")
    ap.add_argument("--register", default="", help="指定语域")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    try:
        raw_cfg = load_json(args.rules)
        cfg = resolve_profile(raw_cfg, args.profile)
        text = read_text(args.article)
    except Exception as e:
        print("[错误] %s" % e, file=sys.stderr)
        return 2

    lines = text.splitlines()
    exempt = cfg.get("exempt_markers", [])
    hard_hits = check_terms(lines, cfg.get("hard_terms", []), exempt, "合规风险词")
    soft_hits = []
    soft_hits += check_terms(lines, cfg.get("ai_taste_phrases", []), exempt, "AI味短语")
    soft_hits += check_regex(lines, cfg.get("regex_groups", []), exempt)

    title = get_title(text, args.article)
    keywords = get_keywords(text)
    ledger = load_ledger(args.ledger)
    dedup = check_dedup(title, keywords, ledger, cfg.get("dedup", {}))

    reg_result, reg_counts = check_register(lines, cfg.get("register_profiles"),
                                            cfg.get("register_min_hits", 3), args.register)

    print("=" * 56)
    print("发布前闸门 · %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("稿件：%s" % args.article)
    print("场景：%s" % cfg.get("_label", cfg.get("_profile", "默认")))
    print("标题：%s" % title)
    print("=" * 56)

    print("\n【硬检查】")
    hard_label_hits = [h for h in hard_hits if h[1] == "合规风险词"]
    if hard_label_hits:
        for ln, label, w, ctx in hard_label_hits:
            print("  拦截 L%d %s：%s  | %s" % (ln, label, w, ctx))
    else:
        print("  通过  合规风险词：无命中")
    dc = cfg.get("dedup", {})
    if dc.get("enabled", True):
        if dedup:
            for score, d, t in dedup:
                print("  拦截 选题重复 %.2f（%s）：%s" % (score, d, t))
        else:
            print("  通过  近 %s 日选题重复：无" % dc.get("window_days", 7))

    print("\n【软提示】")
    if soft_hits:
        for ln, label, w, ctx in soft_hits:
            print("  提示 L%d %s：%s  | %s" % (ln, label, w, ctx))
        print("  共 %d 处，需人工判断，不影响放行。" % len(soft_hits))
    else:
        print("  无提示")

    if reg_result:
        main_reg, foreign = reg_result
        print("\n【语域一致性】提示")
        print("  语域：%s" % main_reg)
        print("  异质标记：%s" % ", ".join("%s(%d)" % (k, v) for k, v in foreign.items()))
    elif args.register:
        print("\n【语域一致性】通过（%s）" % args.register)

    if args.ai:
        print("\n【DeepSeek 终审】正在调用，请稍候…")
        result, err = deepseek_review(text, cfg.get("ai_review", {}))
        if err:
            print("  跳过：%s" % err)
        else:
            print("-" * 56)
            print(result)
            print("-" * 56)

    blocked = bool(hard_hits or dedup)
    print("\n" + "=" * 56)
    if blocked:
        print("结论：拦截。修正硬检查命中项后重跑。")
        return 1
    print("结论：放行。（软提示 %d 处）" % len(soft_hits))
    if not args.no_record:
        append_ledger(args.ledger, title, keywords, args.register)
        print("已写入台账：%s" % args.ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
