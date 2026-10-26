"""调度方案的确定性 Mock 计算。

方案比较只使用结构化输入和明确的约束，不执行泵组、阀门或其他现场写操作。
后续接入真实水力模型时，可以保留结果字段和人工复核边界。
"""

from typing import Any


_RISK_ORDER = {"low": 1, "medium": 2, "high": 3}
_DEFAULT_TARGET_DEMAND = 13_000.0
_DEFAULT_MAX_DELAY = 60.0
_DEFAULT_MAX_LOAD = 90.0


def _number(value: Any, *, field: str, default: float | None = None) -> float:
    """把方案输入转换为有限的非负数。"""

    if value is None and default is not None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是数字") from exc
    if result < 0:
        raise ValueError(f"{field} 不能为负数")
    return result


def _risk(value: Any) -> str:
    result = str(value or "medium").lower()
    if result not in _RISK_ORDER:
        raise ValueError("risk 必须是 low、medium 或 high")
    return result


def compare_scheme_inputs(
    schemes: list[dict],
    *,
    target_demand: float | None = None,
    constraints: dict | None = None,
) -> dict:
    """计算方案指标、约束违反项和可解释评分。"""

    target = _number(target_demand, field="target_demand", default=_DEFAULT_TARGET_DEMAND)
    if target <= 0:
        raise ValueError("target_demand 必须大于 0")
    constraints = constraints or {}
    max_delay = _number(constraints.get("max_delay_minutes"), field="max_delay_minutes", default=_DEFAULT_MAX_DELAY)
    max_load = _number(constraints.get("max_load_percent"), field="max_load_percent", default=_DEFAULT_MAX_LOAD)
    max_risk = _risk(constraints.get("max_risk", "high"))
    if max_delay <= 0 or max_load <= 0:
        raise ValueError("时延和负荷约束必须大于 0")

    prepared: list[dict] = []
    for index, scheme in enumerate(schemes, start=1):
        if not isinstance(scheme, dict):
            raise ValueError(f"第 {index} 个方案必须是对象")
        supply = _number(scheme.get("supply"), field=f"方案 {index} supply", default=0)
        delay = _number(scheme.get("delay_minutes"), field=f"方案 {index} delay_minutes", default=0)
        energy = _number(scheme.get("energy"), field=f"方案 {index} energy", default=0)
        risk = _risk(scheme.get("risk", "medium"))
        load = scheme.get("load_percent", scheme.get("load"))
        load_percent = _number(load, field=f"方案 {index} load_percent", default=55 + min(35, supply / target * 25))
        supply_gap = round(supply - target)
        violations: list[str] = []
        if supply < target * 0.95:
            violations.append(f"供水量低于目标的 95%（目标 {target:.0f} m³/d）")
        if delay > max_delay:
            violations.append(f"预计时延超过 {max_delay:.0f} min")
        if load_percent > max_load:
            violations.append(f"设备负荷超过 {max_load:.0f}%")
        if _RISK_ORDER[risk] > _RISK_ORDER[max_risk]:
            violations.append(f"风险等级高于允许上限 {max_risk}")
        prepared.append(
            {
                "scheme_id": str(scheme.get("scheme_id") or f"scheme-{index}"),
                "name": str(scheme.get("name") or f"方案 {index}"),
                "supply": round(supply),
                "delay_minutes": round(delay),
                "energy": round(energy),
                "load_percent": round(load_percent),
                "risk": risk,
                "supply_gap": supply_gap,
                "feasible": not violations,
                "constraint_violations": violations,
            }
        )

    max_energy = max((item["energy"] for item in prepared), default=1.0) or 1.0
    for item in prepared:
        # 评分越低越好：能耗、时延、供需偏差、负荷和风险分别计入。
        energy_score = item["energy"] / max_energy * 100
        delay_score = item["delay_minutes"] / max_delay * 100
        gap_ratio = abs(item["supply_gap"]) / target * 100
        if item["supply_gap"] > 0:
            gap_ratio *= 0.25
        load_score = item["load_percent"]
        risk_score = _RISK_ORDER[item["risk"]] / _RISK_ORDER[max_risk] * 100
        item["score"] = round(
            0.35 * energy_score
            + 0.20 * delay_score
            + 0.25 * gap_ratio
            + 0.10 * load_score
            + 0.10 * risk_score
            + (1000 if not item["feasible"] else 0),
            1,
        )
        item["calculation_basis"] = [
            "供需偏差 = 方案供水量 - 目标需求量",
            "综合评分权重：能耗 35%、时延 20%、供需偏差 25%、负荷 10%、风险 10%",
        ]

    feasible = [item for item in prepared if item["feasible"]]
    best = min(feasible or prepared, key=lambda item: (item["score"], item["scheme_id"]))
    recommendation = (
        f"建议优先复核{best['name']}：综合评分 {best['score']:.2f}，"
        f"供水量较目标{'增加' if best['supply_gap'] >= 0 else '减少'} {abs(best['supply_gap']):.0f} m³/d。"
    )
    if not feasible:
        recommendation += "当前没有完全满足约束的方案，需人工确认约束或补充方案。"
    return {
        "results": sorted(prepared, key=lambda item: (not item["feasible"], item["score"], item["scheme_id"])),
        "recommended_scheme_id": best["scheme_id"],
        "recommendation": recommendation,
        "target_demand": target,
        "constraints": {
            "max_delay_minutes": max_delay,
            "max_load_percent": max_load,
            "max_risk": max_risk,
        },
        "assumptions": [
            "当前供水量、时延、能耗和负荷来自方案输入或 Mock 缺省值",
            "未接入水力模型，评分仅用于方案草稿比较和人工复核",
            "任何方案都不会生成现场控制指令",
        ],
    }
