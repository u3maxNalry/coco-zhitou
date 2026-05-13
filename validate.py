"""
输出格式验证器
==============
验证智能体输出是否符合比赛要求

运行: python validate.py output.json
"""

import json
import sys
import re


def validate_output(data: list) -> dict:
    """验证输出 JSON 数组是否符合比赛要求"""
    errors = []
    warnings = []

    # 1. 必须是列表
    if not isinstance(data, list):
        return {"valid": False, "errors": ["输出必须是 JSON 数组"]}

    # 2. 空数组是合法的（无操作日）
    if len(data) == 0:
        return {"valid": True, "warnings": ["当日无操作（空数组）"]}

    symbols_seen = set()

    for i, item in enumerate(data):
        prefix = f"[{i}]"

        # 3. 必须是字典
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须是 JSON 对象")
            continue

        # 4. 必须包含 symbol
        if "symbol" not in item:
            errors.append(f"{prefix} 缺少 'symbol' 字段")
            continue

        symbol = str(item["symbol"])
        # 去除可能的非数字字符后检查
        symbol_digits = re.sub(r'\D', '', symbol)

        # 5. symbol 必须是有效的股票代码格式
        if len(symbol_digits) != 6:
            errors.append(f"{prefix} symbol '{symbol}' 清理后长度不是 6 位: '{symbol_digits}'")

        # 6. 检查重复
        if symbol_digits in symbols_seen:
            warnings.append(f"{prefix} symbol '{symbol_digits}' 重复推荐")
        symbols_seen.add(symbol_digits)

        # 7. symbol_name
        if "symbol_name" not in item:
            errors.append(f"{prefix} 缺少 'symbol_name' 字段")

        # 8. volume 必须存在且为正整数
        if "volume" not in item:
            errors.append(f"{prefix} 缺少 'volume' 字段")
            continue

        volume = item["volume"]
        if not isinstance(volume, (int, float)) or volume <= 0:
            errors.append(f"{prefix} volume 必须为正整数, 当前值: {volume}")
            continue

        # 9. volume 必须是 100 的整数倍
        if int(volume) % 100 != 0:
            errors.append(f"{prefix} volume={volume} 不是 100 的整数倍")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": f"验证 {len(data)} 条建议, {len(errors)} 个错误, {len(warnings)} 个警告"
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python validate.py <output.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)

    result = validate_output(data)

    print("=" * 60)
    print("智投未来 · 输出格式验证")
    print("=" * 60)

    if result["valid"]:
        print("✅ 格式验证通过")
    else:
        print("❌ 格式验证失败")

    print(f"\n📊 {result['summary']}")

    if result["errors"]:
        print("\n❌ 错误:")
        for e in result["errors"]:
            print(f"  • {e}")

    if result["warnings"]:
        print("\n⚠️ 警告:")
        for w in result["warnings"]:
            print(f"  • {w}")


if __name__ == "__main__":
    main()
