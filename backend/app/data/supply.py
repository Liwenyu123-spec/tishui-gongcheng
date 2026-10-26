"""片区供需模块共用的 Mock 数据。"""


def vary_supply_areas(areas: list[dict]) -> None:
    """每次查询给供需和压力加一点测试波动，并写回原记录。"""

    import random

    for area in areas:
        supply = float(area.get("supply") or 0)
        demand = float(area.get("demand") or 0)
        pressure = float(area.get("pressure") or 0.4)
        area["supply"] = round(min(20000.0, max(500.0, supply + random.uniform(-180, 180))))
        area["demand"] = round(min(20000.0, max(500.0, demand + random.uniform(-120, 120))))
        area["pressure"] = round(min(1.2, max(0.15, pressure + random.uniform(-0.03, 0.03))), 2)
        balance = area["supply"] - area["demand"]
        area["risk"] = "high" if balance < -400 else "medium" if balance < 0 else "low"


# 片区供需 Mock 数据；balance 由接口根据 supply-demand 计算。
# station_id 用于把片区数据绑定到站点权限范围。
_SUPPLY_AREAS = [
    # 平定城区片区，当前供水量低于需求量。
    {
        "area": "平定城区",
        "station_id": "pump-04",
        "supply": 9200.0,
        "demand": 9800.0,
        "pressure": 0.38,
        "risk": "medium",
    },
    # 东部片区，当前存在少量供水结余。
    {
        "area": "东部片区",
        "station_id": "pump-03",
        "supply": 5600.0,
        "demand": 5200.0,
        "pressure": 0.43,
        "risk": "low",
    },
    # 西部片区，绑定二泵站并用于受限站点账号测试。
    {
        "area": "西部片区",
        "station_id": "pump-02",
        "supply": 4100.0,
        "demand": 4700.0,
        "pressure": 0.31,
        "risk": "high",
    },
]
