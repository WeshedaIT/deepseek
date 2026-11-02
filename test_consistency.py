#!/usr/bin/env python3
"""
test_consistency.py — 保证「静态页 / 数据源 / Python 应用」三者不漂移。

核心校验:
  1. index.html 内联的数据与 data/api_tree.json 完全一致（逐节点比对）
  2. index.html 中的接口数量 == 数据源中的接口数量 == Python 应用统计的数量
  3. 页面没有残留占位符（如 __API_TREE_DATA__ / API_TREE_PLACEHOLDER）
  4. build.py --check 能识别出被手工改动过的 index.html

零第三方依赖，直接 python3 test_consistency.py 运行。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "api_tree.json"
INDEX_FILE = ROOT / "index.html"

failures = []
checks = 0


def check(name: str, ok: bool, detail: str = ""):
    global checks
    checks += 1
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  —  {detail}" if detail else ""))
        failures.append(name)


def load_source() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def inline_payload() -> dict:
    html = INDEX_FILE.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="api-tree-data" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not match:
        raise SystemExit("index.html 中找不到内联数据节点 <script id=\"api-tree-data\">")
    return json.loads(match.group(1))


def count_apis(tree) -> int:
    total = 0
    for node in tree:
        if node.get("type") == "apiDetail":
            total += 1
        total += count_apis(node.get("children") or [])
    return total


def app_api_count() -> int:
    """导入 Python 应用并读取它从同一数据源统计出的接口数。"""
    sys.path.insert(0, str(ROOT))
    import sellfox_explorer

    return sellfox_explorer.Tree(DATA_FILE).stats["apis"]


def main() -> int:
    print("== 数据源 ↔ 静态页 ↔ Python 应用 一致性 ==")

    if not DATA_FILE.exists():
        print(f"FAIL: 缺少 {DATA_FILE}")
        return 1
    if not INDEX_FILE.exists():
        print(f"FAIL: 缺少 {INDEX_FILE}，请运行 python3 build.py")
        return 1

    source = load_source()
    payload = inline_payload()
    src_apis = count_apis(source["tree"])
    page_apis = count_apis(payload["tree"])

    check("数据源接口数 > 0", src_apis > 0, f"apis={src_apis}")

    check(
        "静态页接口数 == 数据源接口数",
        page_apis == src_apis,
        f"page={page_apis} source={src_apis}",
    )

    app_apis = app_api_count()
    check(
        "Python 应用接口数 == 数据源接口数",
        app_apis == src_apis,
        f"app={app_apis} source={src_apis}",
    )

    check(
        "静态页树结构逐节点一致",
        payload["tree"] == source["tree"],
        "index.html 的内联树与 data/api_tree.json 不同，可能已过期",
    )

    modules_src = [n["name"] for n in source["tree"]]
    modules_page = [n["name"] for n in payload["tree"]]
    check("模块清单一致", modules_src == modules_page,
          f"source={len(modules_src)} page={len(modules_page)}")

    html = INDEX_FILE.read_text(encoding="utf-8")
    for marker in ("__API_TREE_DATA__", "API_TREE_PLACEHOLDER", "__API_TREE_PLACEHOLDER__"):
        check(f"无残留占位符 {marker}", marker not in html)

    check(
        "页面无外部脚本/样式依赖",
        not re.search(r'<(script|link)[^>]+(src|href)="https?://', html, re.I),
        "发现外链资源，独立打开时可能失效",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "build.py"), "--check"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    check("build.py --check 通过", result.returncode == 0,
          (result.stdout + result.stderr).strip().splitlines()[-1] if (result.stdout or result.stderr) else "")

    print()
    print(f"接口 {src_apis} / 模块 {len(modules_src)} / 页面 {INDEX_FILE.stat().st_size / 1024:.1f} KB")
    if failures:
        print(f"\n{len(failures)} 项失败，{checks - len(failures)}/{checks} 通过")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n全部 {checks} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
