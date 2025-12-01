import re
from pathlib import Path


def is_date_line(text: str) -> bool:
    """判断一行是否为新的账目日期起始行，例如：2025 年 12 月 1 日 ..."""
    text = text.strip()
    # 典型格式：2025 年 12 月 1 日\tSteam 社区市场
    return bool(re.match(r"^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", text))


def prettify_line(text: str) -> str:
    """对单行做一些简单的可读性增强，不改变语义。"""
    stripped = text.strip()
    if not stripped:
        return ""

    # 将制表符替换为更适合 Markdown 的分隔符
    if "\t" in text:
        # 保留原始前后空白，但中间用 " | " 更易读
        parts = [p.strip() for p in text.split("\t")]
        return " | ".join(p for p in parts if p != "")

    # 对一些关键类型加上列表标记，使层级更清晰
    keywords = {
        "市场交易",
        "购买",
        "游戏内购买",
        "资金",
        "钱包",
        "支付宝",
    }
    if stripped in keywords:
        return f"- {stripped}"

    return text.rstrip()


def format_cost_file(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    out_lines = []
    first_content_written = False

    for idx, raw in enumerate(lines):
        line = raw.rstrip("\n")
        stripped = line.strip()

        if is_date_line(stripped):
            # 在每条记录之间插入分隔线，增强阅读体验
            if first_content_written:
                out_lines.append("")  # 空行
                out_lines.append("---")  # Markdown 分隔线
                out_lines.append("")
            first_content_written = True
            out_lines.append(prettify_line(line))
            continue

        # 其他行照常做轻量 prettify
        if stripped == "":
            out_lines.append("")
        else:
            out_lines.append(prettify_line(line))

    output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def main() -> None:
    input_file = Path("cost.md")
    output_file = Path("cost_formatted.md")
    format_cost_file(input_file, output_file)
    print(f"Formatted file written to: {output_file}")


if __name__ == "__main__":
    main()


