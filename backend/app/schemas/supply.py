"""片区供需接口的请求和响应模型。"""

from pydantic import BaseModel


class SupplyArea(BaseModel):
    """单个片区的供需计算结果。"""

    # 供需片区名称。
    area: str
    # 片区对应的主站点编号。
    station_id: str
    # 统计时段内的供水量。
    supply: float
    # 统计时段内的需水量。
    demand: float
    # 供水量减去需水量后的平衡值。
    balance: float
    # 供需量单位，默认使用每天立方米。
    unit: str = "m³/d"
    # 片区当前压力值。
    pressure: float
    # 片区风险等级或风险说明。
    risk: str
    # 数据来源标记。
    source: str = "mock"


class SupplyBalanceResponse(BaseModel):
    """供需平衡接口的整体响应。"""

    # 统计时段起点。
    from_time: str
    # 统计时段终点。
    to_time: str
    # 各片区的供需明细。
    areas: list[SupplyArea]
    # 所有片区合计供水量。
    total_supply: float
    # 所有片区合计需水量。
    total_demand: float
    # 所有片区合计平衡值。
    total_balance: float
    # 对瓶颈片区和总体风险的文字摘要。
    bottleneck_summary: str
    # 数据来源标记。
    source: str = "mock"
