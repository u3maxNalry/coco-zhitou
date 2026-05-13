"""
智投未来 · 多因子量化投资智能体
====================================
AI4Value 金融投资赛道参赛作品

策略：动量 + 资金流 + 质量 三因子综合评分模型
输出：符合比赛要求的 JSON 格式投资建议

使用方法：
    python agent.py --input data.json
    python agent.py --date 2026-05-13

作者：参赛团队
版本：1.0.0
"""

import json
import math
import sys
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ============================================================
# 配置参数
# ============================================================

@dataclass
class AgentConfig:
    """智能体配置"""
    # 资金管理
    total_capital: float = 500_000.0       # 总资金（元）
    max_single_position_pct: float = 0.20   # 单只股票最大仓位
    min_single_position_pct: float = 0.05   # 单只股票最小仓位
    max_holdings: int = 8                   # 最大持仓数
    min_holdings: int = 2                   # 最小持仓数
    lot_size: int = 100                     # A股最小交易单元

    # 科技股偏好模式
    tech_focus: bool = False                # 是否聚焦科技赛道
    tech_quality_boost: float = 2.5         # 科技股质量得分加成
    tech_only: bool = True                  # True=仅推荐科技股, False=科技股加分但保留其他

    # 因子权重
    weight_momentum: float = 0.40           # 动量因子权重
    weight_capital_flow: float = 0.35       # 资金流因子权重
    weight_quality: float = 0.25            # 质量因子权重

    # 动量因子内部权重
    w_momentum_5d: float = 0.50
    w_momentum_10d: float = 0.30
    w_momentum_20d: float = 0.20

    # 资金流因子内部权重
    w_flow_today: float = 0.40
    w_flow_5d: float = 0.30
    w_volume_ratio: float = 0.30

    # 筛选阈值
    min_avg_daily_amount: float = 10_000_000  # 日均成交额最低（元）
    min_volume_ratio: float = 0.8              # 最低量比
    momentum_threshold: float = 0.0            # 动量得分最低阈值

    # 风控参数
    max_drawdown_pct: float = 0.15             # 最大回撤触发减仓
    market_decline_threshold: float = -0.03    # 市场大跌阈值
    panic_limit_down_count: int = 500          # 恐慌跌停数
    drawdown_reduce_ratio: float = 0.50        # 回撤时仓位缩减比例

    # 打分标准化参数（z-score 用）
    momentum_mean: float = 0.0
    momentum_std: float = 15.0
    flow_mean: float = 0.0
    flow_std: float = 5.0


# ============================================================
# 数据模型
# ============================================================

@dataclass
class MarketSnapshot:
    """市场快照"""
    sh_index: float = 0.0
    sz_index: float = 0.0
    total_volume: float = 0.0
    up_count: int = 0
    down_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0


@dataclass
class Candidate:
    """候选标的"""
    symbol: str
    symbol_name: str
    close: float
    change_pct_5d: float = 0.0
    change_pct_10d: float = 0.0
    change_pct_20d: float = 0.0
    main_net_inflow_today: float = 0.0
    main_net_inflow_5d: float = 0.0
    volume_ratio: float = 1.0
    avg_daily_amount: float = 0.0
    is_st: bool = False
    is_suspended: bool = False
    is_limit_down: bool = False


@dataclass
class ScoredCandidate:
    """打分后的候选标的"""
    candidate: Candidate
    momentum_score: float = 0.0
    capital_flow_score: float = 0.0
    quality_score: float = 0.0
    total_score: float = 0.0


@dataclass
class Recommendation:
    """投资建议"""
    symbol: str
    symbol_name: str
    volume: int


@dataclass
class DecisionContext:
    """决策上下文"""
    date: str
    total_capital: float
    current_positions: List[Dict]
    market_snapshot: MarketSnapshot
    candidates: List[Candidate]


# ============================================================
# 科技股分类
# ============================================================

# A股科技赛道标的库（可按需扩充）
TECH_SYMBOLS = {
    # 创业板科技
    "300750", "300059", "300124", "300274", "300033", "300782",
    "300014", "300661", "300223", "300458",
    # 科创板硬科技
    "688981", "688012", "688111", "688036", "688008", "688256",
    # 电子/半导体
    "000725", "002475", "002415", "002371", "603986",
    "600703", "002049", "300327",
    # 新能源科技
    "002594", "601012", "688599",
    # AI/软件/通信
    "002230", "300308", "300502", "000063", "600536",
    # 机器人/自动化
    "300024", "002747", "688017",
}

def is_tech_stock(symbol: str, name: str = "") -> bool:
    """判断是否为科技股（基于代码前缀 + 名称 + 已知标的库）"""
    tech_keywords = [
        "电子", "科技", "光电", "半导体", "芯片", "集成", "微", "纳米",
        "软件", "数据", "智能", "机器人", "自动", "传感", "激光",
        "通信", "网络", "信息", "互联", "云", "算力",
        "新能源", "光伏", "锂电", "储能", "电池", "充电",
        "生物", "医药", "基因", "制药",
    ]
    s = str(symbol).replace(".", "").zfill(6)[:6]

    # 1) 已知科技标的库
    if s in TECH_SYMBOLS:
        return True

    # 2) 创业板 300 / 科创板 688 默认为科技
    if s.startswith("300") or s.startswith("688"):
        return True

    # 3) 按名称中的科技关键词匹配
    for kw in tech_keywords:
        if kw in name:
            return True

    return False




class FactorEngine:
    """多因子计算引擎"""

    def __init__(self, config: AgentConfig):
        self.config = config

    def compute_momentum_score(self, c: Candidate) -> float:
        """计算动量因子得分"""
        w = self.config
        raw = (
            w.w_momentum_5d * c.change_pct_5d +
            w.w_momentum_10d * c.change_pct_10d +
            w.w_momentum_20d * c.change_pct_20d
        )
        # z-score 标准化
        return (raw - w.momentum_mean) / max(w.momentum_std, 0.01)

    def compute_capital_flow_score(self, c: Candidate) -> float:
        """计算资金流因子得分"""
        w = self.config
        # 主力资金净流入率（简化为除以日均成交额估算）
        avg_amount = max(c.avg_daily_amount, 1_000_000)
        inflow_rate_today = c.main_net_inflow_today / avg_amount * 100
        inflow_rate_5d = c.main_net_inflow_5d / (avg_amount * 5) * 100

        raw = (
            w.w_flow_today * inflow_rate_today +
            w.w_flow_5d * inflow_rate_5d +
            w.w_volume_ratio * (c.volume_ratio - 1.0) * 10
        )
        return (raw - w.flow_mean) / max(w.flow_std, 0.01)

    def compute_quality_score(self, c: Candidate) -> float:
        """计算质量因子得分"""
        score = 0.0

        # 一票否决项
        if c.is_st:
            return -100.0
        if c.is_suspended:
            return -100.0
        if c.is_limit_down:
            return -100.0

        # 流动性评分
        if c.avg_daily_amount >= 500_000_000:
            score += 2.0
        elif c.avg_daily_amount >= 100_000_000:
            score += 1.0
        elif c.avg_daily_amount >= self.config.min_avg_daily_amount:
            score += 0.0
        else:
            score -= 1.0

        # 量比健康度
        if 1.0 <= c.volume_ratio <= 3.0:
            score += 1.0
        elif c.volume_ratio > 5.0:
            score -= 0.5  # 异常放量风险

        # 科技股偏好加成
        if self.config.tech_focus and is_tech_stock(c.symbol, c.symbol_name):
            score += self.config.tech_quality_boost

        return score

    def compute_total_score(self, c: Candidate) -> ScoredCandidate:
        """计算综合得分"""
        momentum = self.compute_momentum_score(c)
        capital_flow = self.compute_capital_flow_score(c)
        quality = self.compute_quality_score(c)

        w = self.config
        total = (
            w.weight_momentum * momentum +
            w.weight_capital_flow * capital_flow +
            w.weight_quality * quality
        )

        return ScoredCandidate(
            candidate=c,
            momentum_score=round(momentum, 3),
            capital_flow_score=round(capital_flow, 3),
            quality_score=round(quality, 3),
            total_score=round(total, 3),
        )


# ============================================================
# 风控引擎
# ============================================================

class RiskEngine:
    """风险管理引擎"""

    def __init__(self, config: AgentConfig):
        self.config = config

    def assess_market_risk(self, market: MarketSnapshot) -> Tuple[bool, str]:
        """
        评估市场风险等级
        返回：(是否可交易, 风险说明)
        """
        # 恐慌检测
        if market.limit_down_count >= self.config.panic_limit_down_count:
            return False, f"市场极端恐慌：跌停数 {market.limit_down_count} >= {self.config.panic_limit_down_count}"

        # 流动性检测
        if market.total_volume <= 0:
            return False, "市场无成交数据"

        # 涨跌比检测
        total = market.up_count + market.down_count
        if total > 0:
            down_ratio = market.down_count / total
            if down_ratio > 0.85:
                return False, f"市场普跌：下跌占比 {down_ratio:.1%}"

        return True, "市场风险正常"

    def should_reduce_position(self, current_drawdown_pct: float) -> Tuple[bool, float]:
        """
        判断是否需要缩减仓位
        返回：(是否缩减, 缩减后仓位比例)
        """
        if current_drawdown_pct >= self.config.max_drawdown_pct:
            return True, self.config.drawdown_reduce_ratio
        return False, 1.0

    def check_market_decline(self, market: MarketSnapshot) -> bool:
        """检测市场是否大跌（当日不新增买入）"""
        # 这里简化处理：如果跌停数超过一定比例
        total = market.up_count + market.down_count
        if total > 0:
            down_ratio = market.down_count / total
            if down_ratio > 0.70:
                return True
        return False


# ============================================================
# 仓位管理引擎
# ============================================================

class PositionEngine:
    """仓位管理引擎"""

    def __init__(self, config: AgentConfig):
        self.config = config

    def allocate(self, scored_candidates: List[ScoredCandidate],
                 available_capital: float) -> List[Recommendation]:
        """
        基于得分进行仓位分配
        采用得分加权 + 约束校验的方式
        """
        if not scored_candidates:
            return []

        cfg = self.config
        n = len(scored_candidates)
        n_select = min(n, cfg.max_holdings)
        n_select = max(n_select, min(cfg.min_holdings, n))

        # 取 Top-N
        selected = scored_candidates[:n_select]

        # 计算得分权重（softmax）
        scores = [max(s.total_score, 0.01) for s in selected]
        total_score = sum(scores)
        weights = [s / total_score for s in scores]

        recommendations = []
        for i, sc in enumerate(selected):
            c = sc.candidate
            # 分配资金
            allocated_capital = available_capital * weights[i]

            # 应用仓位上下限
            max_cap = available_capital * cfg.max_single_position_pct
            min_cap = available_capital * cfg.min_single_position_pct
            allocated_capital = min(allocated_capital, max_cap)
            allocated_capital = max(allocated_capital, min_cap)

            # 计算股数（100股整数倍）
            if c.close <= 0:
                continue
            raw_volume = int(allocated_capital / c.close)
            volume = (raw_volume // cfg.lot_size) * cfg.lot_size

            if volume < cfg.lot_size:
                continue

            recommendations.append(Recommendation(
                symbol=str(c.symbol).replace(".", "").zfill(6)[:6],
                symbol_name=c.symbol_name,
                volume=volume,
            ))

        return recommendations


# ============================================================
# 主智能体
# ============================================================

class ZhiTouAgent:
    """智投未来 · 多因子量化投资智能体"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.factor_engine = FactorEngine(self.config)
        self.risk_engine = RiskEngine(self.config)
        self.position_engine = PositionEngine(self.config)
        self.decision_log: List[str] = []

    def log(self, msg: str):
        """记录决策日志"""
        self.decision_log.append(msg)

    def get_decision_log(self) -> str:
        """获取决策日志"""
        return "\n".join(self.decision_log)

    def decide(self, context: DecisionContext) -> Tuple[List[Recommendation], str]:
        """
        核心决策函数

        参数:
            context: 包含市场数据、候选标的、当前持仓等信息

        返回:
            (投资建议列表, 决策日志)
        """
        self.decision_log = []
        cfg = self.config

        self.log(f"========== 决策日期: {context.date} ==========")
        self.log(f"可用资金: {context.total_capital:,.0f} 元")
        self.log(f"候选标的数: {len(context.candidates)}")

        # ---- Step 1: 市场风险评估 ----
        can_trade, risk_msg = self.risk_engine.assess_market_risk(
            context.market_snapshot
        )
        self.log(f"市场风险评估: {'✅ 可交易' if can_trade else '❌ 不可交易'} - {risk_msg}")

        if not can_trade:
            self.log("决策: 市场风险过高，空仓观望")
            return [], self.get_decision_log()

        # ---- Step 2: 市场大跌检测 ----
        if self.risk_engine.check_market_decline(context.market_snapshot):
            self.log("决策: 市场大跌，当日不新增买入")
            return [], self.get_decision_log()

        # ---- Step 3: 基础过滤 ----
        valid_candidates = []
        tech_count = 0
        for c in context.candidates:
            # 科技聚焦模式：仅保留科技股
            if cfg.tech_focus and cfg.tech_only:
                if not is_tech_stock(c.symbol, c.symbol_name):
                    self.log(f"  过滤 非科技: {c.symbol_name}({c.symbol})")
                    continue
            tech_count += 1
            # 排除 ST/停牌
            if c.is_st:
                self.log(f"  过滤 ST: {c.symbol_name}({c.symbol})")
                continue
            if c.is_suspended:
                self.log(f"  过滤 停牌: {c.symbol_name}({c.symbol})")
                continue
            if c.is_limit_down:
                self.log(f"  过滤 跌停: {c.symbol_name}({c.symbol})")
                continue
            # 流动性过滤
            if c.avg_daily_amount < cfg.min_avg_daily_amount:
                self.log(f"  过滤 流动性不足: {c.symbol_name}({c.symbol})")
                continue
            # 量比过滤
            if c.volume_ratio < cfg.min_volume_ratio:
                self.log(f"  过滤 量比不足: {c.symbol_name}({c.symbol})")
                continue
            valid_candidates.append(c)

        self.log(f"基础过滤后剩余: {len(valid_candidates)} 只")

        if len(valid_candidates) < cfg.min_holdings:
            self.log(f"决策: 有效候选不足 {cfg.min_holdings} 只，空仓观望")
            return [], self.get_decision_log()

        # ---- Step 4: 因子计算与综合评分 ----
        scored = []
        for c in valid_candidates:
            sc = self.factor_engine.compute_total_score(c)
            if sc.total_score > cfg.momentum_threshold:
                scored.append(sc)

        # 按总分降序排列
        scored.sort(key=lambda x: x.total_score, reverse=True)

        self.log(f"综合评分后入选: {len(scored)} 只")
        for i, sc in enumerate(scored[:10]):
            self.log(
                f"  #{i+1} {sc.candidate.symbol_name}({sc.candidate.symbol}) "
                f"动量={sc.momentum_score:.2f} "
                f"资金流={sc.capital_flow_score:.2f} "
                f"质量={sc.quality_score:.2f} "
                f"总分={sc.total_score:.2f}"
            )

        if not scored:
            self.log("决策: 无标的通过综合评分筛选")
            return [], self.get_decision_log()

        # ---- Step 5: 仓位分配 ----
        recommendations = self.position_engine.allocate(
            scored, context.total_capital
        )

        total_allocated = sum(
            r.volume * next(
                (c.close for c in context.candidates if c.symbol == r.symbol),
                0
            )
            for r in recommendations
        )
        self.log(f"最终推荐: {len(recommendations)} 只, 预估占用资金: {total_allocated:,.0f} 元")

        return recommendations, self.get_decision_log()

    def decide_json(self, context: DecisionContext) -> str:
        """决策并输出 JSON 格式结果"""
        recommendations, log = self.decide(context)
        result = [
            {
                "symbol": r.symbol,
                "symbol_name": r.symbol_name,
                "volume": r.volume,
            }
            for r in recommendations
        ]
        return json.dumps(result, ensure_ascii=False)


# ============================================================
# 数据解析
# ============================================================

def parse_input(data: dict) -> DecisionContext:
    """从 JSON 输入解析决策上下文"""
    market_raw = data.get("market_snapshot", {})
    market = MarketSnapshot(
        sh_index=market_raw.get("sh_index", 0),
        sz_index=market_raw.get("sz_index", 0),
        total_volume=market_raw.get("total_volume", 0),
        up_count=market_raw.get("up_count", 0),
        down_count=market_raw.get("down_count", 0),
        limit_up_count=market_raw.get("limit_up_count", 0),
        limit_down_count=market_raw.get("limit_down_count", 0),
    )

    candidates = []
    for c_raw in data.get("candidates", []):
        candidates.append(Candidate(
            symbol=str(c_raw.get("symbol", "")),
            symbol_name=c_raw.get("symbol_name", ""),
            close=float(c_raw.get("close", 0)),
            change_pct_5d=float(c_raw.get("change_pct_5d", 0)),
            change_pct_10d=float(c_raw.get("change_pct_10d", 0)),
            change_pct_20d=float(c_raw.get("change_pct_20d", 0)),
            main_net_inflow_today=float(c_raw.get("main_net_inflow_today", 0)),
            main_net_inflow_5d=float(c_raw.get("main_net_inflow_5d", 0)),
            volume_ratio=float(c_raw.get("volume_ratio", 1.0)),
            avg_daily_amount=float(c_raw.get("avg_daily_amount", 0)),
            is_st=bool(c_raw.get("is_st", False)),
            is_suspended=bool(c_raw.get("is_suspended", False)),
            is_limit_down=bool(c_raw.get("is_limit_down", False)),
        ))

    return DecisionContext(
        date=data.get("date", ""),
        total_capital=float(data.get("total_capital", 500000)),
        current_positions=data.get("current_positions", []),
        market_snapshot=market,
        candidates=candidates,
    )


# ============================================================
# 测试示例
# ============================================================

def generate_sample_data() -> dict:
    """生成示例输入数据用于测试"""
    import random
    random.seed(42)

    symbols = [
        ("000001", "平安银行"), ("600519", "贵州茅台"), ("000858", "五粮液"),
        ("300750", "宁德时代"), ("601318", "中国平安"), ("600036", "招商银行"),
        ("000333", "美的集团"), ("002415", "海康威视"), ("600276", "恒瑞医药"),
        ("300059", "东方财富"), ("601012", "隆基绿能"), ("002594", "比亚迪"),
        ("600900", "长江电力"), ("000568", "泸州老窖"), ("300124", "汇川技术"),
        ("600809", "山西汾酒"), ("000725", "京东方A"), ("002475", "立讯精密"),
        ("601888", "中国中免"), ("300274", "阳光电源"),
    ]

    candidates = []
    for symbol, name in symbols:
        base_price = random.uniform(5, 300)
        candidates.append({
            "symbol": symbol,
            "symbol_name": name,
            "close": round(base_price, 2),
            "change_pct_5d": round(random.uniform(-8, 12), 2),
            "change_pct_10d": round(random.uniform(-12, 18), 2),
            "change_pct_20d": round(random.uniform(-15, 25), 2),
            "main_net_inflow_today": random.uniform(-50000000, 100000000),
            "main_net_inflow_5d": random.uniform(-100000000, 200000000),
            "volume_ratio": round(random.uniform(0.5, 3.0), 2),
            "avg_daily_amount": random.uniform(50_000_000, 5_000_000_000),
            "is_st": random.random() < 0.05,
            "is_suspended": random.random() < 0.03,
            "is_limit_down": random.random() < 0.08,
        })

    return {
        "date": "2026-05-13",
        "total_capital": 500000,
        "current_positions": [],
        "market_snapshot": {
            "sh_index": 3350.25,
            "sz_index": 11200.50,
            "total_volume": 95000000000,
            "up_count": 2800,
            "down_count": 1500,
            "limit_up_count": 52,
            "limit_down_count": 8,
        },
        "candidates": candidates,
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="智投未来 · 多因子量化投资智能体",
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="输入 JSON 文件路径",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="2026-05-13",
        help="决策日期",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="使用示例数据运行",
    )
    parser.add_argument(
        "--tech", "-t",
        action="store_true",
        help="聚焦科技赛道：仅推荐科技股并给予质量加成",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细决策日志",
    )

    args = parser.parse_args()

    # 加载数据
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif args.sample:
        data = generate_sample_data()
    else:
        print("请指定 --input <文件路径> 或使用 --sample 运行示例", file=sys.stderr)
        sys.exit(1)

    # 解析并决策
    context = parse_input(data)
    context.date = args.date

    config = AgentConfig(
        tech_focus=args.tech,
        tech_only=args.tech,
    )
    agent = ZhiTouAgent(config=config)
    recommendations, log = agent.decide(context)

    # 输出结果
    if args.verbose:
        print(log, file=sys.stderr)
        print("\n" + "=" * 60, file=sys.stderr)
        print("投资建议 (JSON):", file=sys.stderr)

    print(agent.decide_json(context))


if __name__ == "__main__":
    main()
