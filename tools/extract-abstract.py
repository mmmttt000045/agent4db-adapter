#!/usr/bin/env python3
"""从 overleaf/main.tex 提取摘要（中英文），展开 gen/ 下的数值宏，写成 overleaf/abstract-zh.md。

用法：python3 tools/extract-abstract.py [--tex overleaf/main.tex] [--out overleaf/abstract-zh.md]
"""

import argparse
import os
import re


def braced(s, i):
    """s[i] == '{'：返回与之匹配的 '}' 之后的位置与括号内文本。"""
    assert s[i] == "{"
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{" and (j == 0 or s[j - 1] != "\\"):
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return j + 1, s[i + 1:j]
    raise ValueError("unbalanced braces")


def macros(gen):
    m = {"system": "MAVRA"}
    for f in os.listdir(gen):
        if f.endswith(".tex"):
            for name, val in re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*(?:\{,\}[^{}]*)*)\}", open(os.path.join(gen, f), encoding="utf-8").read()):
                m[name] = val
    return m


def plain(t, m):
    t = re.sub(r"\\([A-Za-z]+)(\\ |\{\})?",
               lambda x: m[x.group(1)] + (" " if x.group(2) == "\\ " else "") if x.group(1) in m else x.group(0), t)
    t = t.replace("{,}", ",").replace("\\%", "%").replace("--", "–").replace("~", " ").replace("\\ ", " ")
    t = re.sub(r"\\(emph|code|textbf)\{([^{}]*)\}", r"\2", t)
    t = re.sub(r"\s*\\cite\{[^}]*\}", "", t)
    return t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", default="overleaf/main.tex")
    ap.add_argument("--out", default="overleaf/abstract-zh.md")
    o = ap.parse_args()
    s = open(o.tex, encoding="utf-8").read()
    m = macros(os.path.join(os.path.dirname(o.tex), "gen"))
    a = s[s.index("\\begin{abstract}"):s.index("\\end{abstract}")]
    i = a.index("\\bi{") + 3
    i, en = braced(a, i)
    i = a.index("{", i)
    _, zh = braced(a, i)
    title = re.search(r"\\title\{\\system: ([^}]*)\}", s).group(1)
    sub = re.search(r"\\subtitle\{([^}]*)\}", s).group(1)
    out = (f"# MAVRA：{sub}\n\nEnglish title: **MAVRA: {title}**\n\n"
           "> 当前摘要，由 `tools/extract-abstract.py` 从 main.tex 提取（数值宏已展开，来自 gen/）。\n\n"
           f"{plain(zh, m)}\n\n---\n\n{plain(en, m)}\n")
    open(o.out, "w", encoding="utf-8").write(out)
    print(out)


if __name__ == "__main__":
    main()
