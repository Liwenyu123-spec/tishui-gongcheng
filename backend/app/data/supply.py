"""片区供需模块共用的 Mock 数据。"""


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
