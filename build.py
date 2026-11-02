#!/usr/bin/env python3
"""
build.py — 生成完全独立的 index.html。

单一数据源: data/api_tree.json
产物:       index.html (自包含，双击即可打开，无需网络/服务器/build 步骤)

用法:
    python3 build.py            # 生成 index.html
    python3 build.py --check    # 只校验 index.html 与数据源是否同步
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "api_tree.json"
TEMPLATE_FILE = ROOT / "src" / "explorer.html"
OUT_FILE = ROOT / "index.html"

PLACEHOLDER = "__API_TREE_DATA__"
BUILD_MARKER = "data-build-hash"


def load_data() -> dict:
    with DATA_FILE.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data.get("tree"), list) or not data["tree"]:
        raise SystemExit(f"{DATA_FILE} 缺少有效的 tree 数组")
    return data


def compute_stats(tree: list) -> dict:
    """从树本身推导统计，避免依赖可能过期的 stats 字段。"""
    stats = {"apis": 0, "folders": 0, "docs": 0, "modules": len(tree)}

    def walk(nodes):
        for node in nodes:
            kind = node.get("type")
            if kind == "apiDetail":
                stats["apis"] += 1
            elif kind == "apiDetailFolder":
                stats["folders"] += 1
            elif kind == "doc":
                stats["docs"] += 1
            walk(node.get("children") or [])

    walk(tree)
    return stats


def payload_json(data: dict, stats: dict) -> str:
    """序列化为可安全内联进 <script> 的 JSON。"""
    body = {
        "source": data.get("source", ""),
        "projectId": data.get("projectId"),
        "stats": stats,
        "tree": data["tree"],
    }
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    # 防止提前闭合 script 标签 / 干扰 HTML 解析
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def render(data: dict) -> tuple:
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"模板 {TEMPLATE_FILE} 缺少占位符 {PLACEHOLDER}")

    stats = compute_stats(data["tree"])
    payload = payload_json(data, stats)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    html = template.replace(PLACEHOLDER, payload)
    html = html.replace(
        "</head>",
        f'<meta name="{BUILD_MARKER}" content="{digest}">\n</head>',
        1,
    )
    return html, stats, digest


def main() -> int:
    parser = argparse.ArgumentParser(description="生成独立的 index.html")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅校验现有 index.html 是否与 data/api_tree.json 同步",
    )
    args = parser.parse_args()

    data = load_data()
    html, stats, digest = render(data)

    if args.check:
        if not OUT_FILE.exists():
            print("FAIL: index.html 不存在，请运行 python3 build.py")
            return 1
        current = OUT_FILE.read_text(encoding="utf-8")
        match = re.search(rf'<meta name="{BUILD_MARKER}" content="([0-9a-f]+)">', current)
        if not match:
            print("FAIL: index.html 缺少构建标记，可能是手工编辑或旧版本")
            return 1
        if match.group(1) != digest:
            print(f"FAIL: index.html 已过期 (页面 {match.group(1)} != 数据 {digest})")
            print("      请运行 python3 build.py")
            return 1
        print(f"OK: index.html 与数据源同步 ({digest})")
        print(
            "    {apis} API / {folders} 分组 / {docs} 文档 / {modules} 模块".format(**stats)
        )
        return 0

    OUT_FILE.write_text(html, encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"已生成 {OUT_FILE.relative_to(ROOT)}  ({size_kb:.1f} KB)")
    print("    {apis} API / {folders} 分组 / {docs} 文档 / {modules} 模块".format(**stats))
    print(f"    build {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
