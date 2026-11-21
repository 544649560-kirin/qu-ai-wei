# 去AI味工具 · AI味检测 · 发布前闸门（preflight）

中文写作的 AI味检测和去AI味自检工具：查 AI 味套话、空泛排比、升华句、同族变体和合规风险词。浏览器打开即用，粘贴稿子当场出结果，不用安装、不上传稿件。

命令行版另支持近 7 日选题去重、语域一致性检查和 DeepSeek 终审；通过后自动把选题写进台账，台账自己长，不用手动维护。

另有**浏览器版**（`index.html`）：打开网页、粘贴稿子、当场出结果。不上传、不保存、不用装任何东西。适合直接发给别人用。

## 为什么做这个

AI 作品大多停在"能生成"，很少有人算"发出去会不会出问题"。这个工具只解决后者：把每次发稿前那些靠人眼扫的动作，收成一个固定入口。高频、结果可判、不换地方——这是它成立的三个条件。

## 两种用法

| | 浏览器版 | 命令行版 |
|---|---|---|
| 安装 | 无 | Python 3.6+ |
| 检查项 | 短语、变体、场景词、语域 | 全部，另加选题去重、DeepSeek 终审 |
| 稿件去向 | 只在本地浏览器，不上传 | 本地文件 |
| 适合 | 发给别人、随手检查 | 自己的日常流水线 |

## 安装（命令行版）

只需要 Python 3.6+。DeepSeek 终审额外需要 `requests`：

```bash
pip3 install requests   # 只在用 --ai 时需要
```

把整个目录拷到任意机器即可，没有绝对路径依赖。

## 用法

```bash
# 常规检查（md / txt / html 都支持，默认通用场景）
python3 preflight.py 稿件.md

# 用场景包
python3 preflight.py 稿件.md --profile 公众号

# 指定语域，检查是否混进别的写法
python3 preflight.py 稿件.md --profile 公众号 --register 经史笔记

# 额外跑 DeepSeek 终审（慢，有 API 成本）
python3 preflight.py 稿件.md --ai

# 检查通过但不写入台账（试跑时用）
python3 preflight.py 稿件.md --no-record

# 换规则库 / 换台账
python3 preflight.py 稿件.md --rules my_rules.json --ledger my_ledger.csv
```

可用的语域：`快讯体`、`经史笔记`、`社会理论`。不指定时自动识别。

## 退出码

| 码 | 含义 | 用途 |
|---|---|---|
| 0 | 放行 | 可发布，已写入台账 |
| 1 | 拦截 | 硬规则命中，修正后重跑 |
| 2 | 参数或文件错误 | 检查命令和路径 |

软提示不影响退出码，只打印提示。这是有意设计：误报一多，闸门就会被绕过。

## 检查项

**硬检查（拦截）**
- 合规风险词：涉房唱衰、就业民生片面化等，词表在 `rules.json → hard.legal_terms`
- 近 7 日选题重复：字符 2-gram Jaccard，阈值 0.55，标题与关键词都参与

**软检查（提示）**
- AI 味短语：结论腔、拟人修辞、作者出面手势等 50+ 条
- 同族变体：正则兜底，抓短语级换皮
- 语域一致性：识别主导语域后，报出异质标记

含 `需要说明`、`数据显示` 等澄清标记的行自动豁免，词表在 `rules.json → exempt_markers`。

## 场景包

`rules.json` 是 v2 结构，分通用底座和场景包。默认是**通用**——只查所有中文写作都适用的套话，不误伤别人的稿子。

| 场景 | 命令参数 | 作用 |
|---|---|---|
| 通用中文写作 | 默认 / `--profile 通用` | 只查 AI 味套话，任何人可用 |
| 公众号写作 | `--profile 公众号` | 加语域串味检查 |
| 财经房产 | `--profile 财经房产` | 加合规风险词（硬拦截） |

网页版顶部下拉框选同样的三个场景。

## 改规则

全部在 `rules.json`，不用改代码：

- 加通用 AI 味词 → `base.ai_taste_phrases`
- 加通用变体正则 → `base.regex_groups`
- 给某场景加合规词 → `profiles.<场景>.hard_terms`
- 给某场景加语域 → `profiles.<场景>.register_profiles`
- 调去重灵敏度 → `dedup.threshold`（调高更严格，0.7 只报几乎相同的）
- 改完网页版 → 重新把 `base` 和 `profiles` 内嵌进 `index.html` 的 `const DATA`（命令行读文件，网页读内嵌数据）

## DeepSeek 终审配置

按优先级读取：

1. 环境变量 `DEEPSEEK_API_KEY`
2. 文件 `~/.workbuddy/deepseek_api_key`（纯文本一行）

密钥不写进本目录，拷给别人不会泄露。

## 导入历史选题

新机器上台账是空的，先把以前发过的稿子导进去：

```bash
# 导入整个目录的 md，日期从文件名或正文提取
python3 import_ledger.py /path/to/articles --ledger ledger.csv

# 只导最近 30 天
python3 import_ledger.py /path/to/articles --days 30

# 换匹配模式
python3 import_ledger.py /path/to/articles --glob "article_*.md"
```

每条二级标题作为一条选题。重复运行按 (日期, 标题) 去重，不会写重。

## 文件说明

| 文件 | 作用 |
|---|---|
| `preflight.py` | 主脚本，所有检查的编排 |
| `rules.json` | 规则库，改检查项只动这里 |
| `import_ledger.py` | 历史稿件导入工具 |
| `ledger.csv` | 选题台账，自动增长 |

## 一个提醒

闸门只判"能不能发"，不判"值不值得发"。后者靠人。
