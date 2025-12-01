import re
from decimal import Decimal, getcontext
from pathlib import Path
from typing import List, Tuple


getcontext().prec = 12  # 足够精度即可

DATE_PATTERN = re.compile(r"^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")


def is_date_line(text: str) -> bool:
    return bool(DATE_PATTERN.match(text.strip()))


def split_blocks(lines: List[str]) -> List[List[str]]:
    """根据日期行把整份账单拆成一条条记录（block）。"""
    blocks: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        if is_date_line(line):
            if current:
                blocks.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
            else:
                # 文件开头的一些非记录内容（标题等），单独作为一个 block
                current = [line]
    if current:
        blocks.append(current)
    return blocks


def extract_amounts(text: str) -> List[Decimal]:
    """从一行中提取所有金额（忽略正负号，只看绝对值）。"""
    result: List[Decimal] = []
    for m in re.finditer(r"[+-]?\s*[¥￥]\s*([\d,.]+)", text):
        num_str = m.group(1).replace(",", "")
        try:
            result.append(Decimal(num_str))
        except Exception:
            continue
    return result


def is_market_block(block: List[str]) -> bool:
    has_market = any("Steam 社区市场" in l for l in block)
    has_funds = any("资金" in l for l in block)
    has_plus = any("+¥" in l or "+￥" in l for l in block)
    return has_market and has_funds and has_plus


EXTERNAL_METHOD_KEYWORDS = [
    "支付宝",
    "微信支付",
    "微信",
    "银行卡",
    "银联",
    "China UnionPay",
    "Visa",
    "MasterCard",
    "American Express",
]


def has_external_method(block: List[str]) -> bool:
    return any(
        any(k in line for k in EXTERNAL_METHOD_KEYWORDS)
        for line in block
    )


def calc_external_for_block(block: List[str]) -> Tuple[Decimal, Decimal]:
    """
    返回 (外部真实花费, 市场交易获得余额)。

    - 外部花费：支付宝/微信/银行卡直付 + 视为 9 折充值的市场收入折算值
    - 市场收入：Steam 市场“资金”项中的 +¥ 金额总和
    """
    external = Decimal("0")
    market_income = Decimal("0")

    # 1. 先处理市场交易获得的余额
    if is_market_block(block):
        for line in block:
            for m in re.finditer(r"\+\s*[¥￥]\s*([\d,.]+)", line):
                num_str = m.group(1).replace(",", "")
                try:
                    market_income += Decimal(num_str)
                except Exception:
                    continue

    # 2. 再处理支付宝/微信/银行卡等外部支付
    if has_external_method(block):
        # Step 1: 行中既有“支付方式关键字”又有金额的情况
        external_step1 = Decimal("0")
        for line in block:
            if any(k in line for k in EXTERNAL_METHOD_KEYWORDS) and "¥" in line:
                amts = extract_amounts(line)
                if amts:
                    external_step1 += sum(amts)

        external += external_step1

        # Step 2: 若上一步没找到（典型如 Kingdom Come 这种），
        #         则找「有金额、但不含 '钱包' / '余额' / '变更' 且不含 '+¥' / '-¥'」的行
        if external_step1 == 0:
            external_step2 = Decimal("0")
            for line in block:
                if "¥" not in line:
                    continue
                if any(w in line for w in ("钱包", "余额", "变更")):
                    continue
                if "+¥" in line or "+￥" in line or "-¥" in line or "-￥" in line:
                    continue
                amts = extract_amounts(line)
                if amts:
                    external_step2 += sum(amts)
            external += external_step2

            # Step 3: 如果依然没找到，则视为充值记录（例如“已购买 XX 钱包资金”）
            #         此时取包含 +¥/-¥ 且有多笔金额的行的第一笔金额作为充值总额
            if external_step2 == 0:
                best: Decimal | None = None
                for line in block:
                    if "+¥" not in line and "+￥" not in line and "-¥" not in line and "-￥" not in line:
                        continue
                    amts = extract_amounts(line)
                    if len(amts) >= 1:
                        first = amts[0]
                        if best is None or first > best:
                            best = first
                if best is not None:
                    external += best

    return external, market_income


def detect_current_wallet_balance(lines: List[str]) -> Decimal | None:
    """
    从整份文件里推测当前 Steam 钱包余额：
    - 取从上到下遇到的第一行，包含至少 3 个金额的行的第 3 个金额
    - 该行通常形如：¥ 76.80\t-¥ 31.37\t¥ 0.00
    """
    for line in lines:
        amts = extract_amounts(line)
        if len(amts) >= 3:
            return amts[2]
    return None


def main() -> None:
    raw_path = Path("cost.md")
    text = raw_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    blocks = split_blocks(lines)

    total_external = Decimal("0")
    total_market_income = Decimal("0")

    for block in blocks:
        external, market_income = calc_external_for_block(block)
        total_external += external
        total_market_income += market_income

    # 市场交易获得余额按 9 折折算为“当初成本”
    cost_from_market = (total_market_income * Decimal("0.9")).quantize(Decimal("0.01"))
    direct_external = (total_external).quantize(Decimal("0.01"))
    total_cost = (direct_external + cost_from_market).quantize(Decimal("0.01"))

    current_balance = detect_current_wallet_balance(lines)

    print("\n")
    print("====== 统计结果（基于 cost.md）======")
    print(f"倒余额获得余额总额：{total_market_income:.2f} 元")
    print(f"按九折计算的倒余额成本：{cost_from_market:.2f} 元")
    print(f"直充直购总额（支付宝/微信/银行卡等）：{direct_external:.2f} 元")
    print("-----------------------------------")
    print(f"估算累计总花费：{total_cost:.2f} 元")
    if current_balance is not None:
        print(f"当前 Steam 钱包余额（按账单推测）：{current_balance:.2f} 元")
    else:
        print("未能从账单中可靠推断当前 Steam 钱包余额。")
    print("如统计明显有误，请检查账单是否完整粘贴")
    print("=====================================")
    print("\n")

if __name__ == "__main__":
    main()


