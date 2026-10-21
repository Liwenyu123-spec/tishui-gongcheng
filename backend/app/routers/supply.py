"""片区供需查询路由。"""

from fastapi import APIRouter, Depends, Query

from ..data.repositories import get_data_source
from ..dependencies import require_roles, user_has_station_access
from ..schemas.supply import SupplyArea, SupplyBalanceResponse

# 供需接口统一挂在 /api/v1 下，前端通过同一 Token 访问。
router = APIRouter(prefix="/api/v1", tags=["供需"])
data_source = get_data_source()


@router.get("/supply/balance", response_model=SupplyBalanceResponse)
def supply_balance(
    from_time: str | None = Query(default=None, alias="from", max_length=64),
    to_time: str | None = Query(default=None, alias="to", max_length=64),
    user: dict = Depends(require_roles("admin", "operator")),
) -> SupplyBalanceResponse:
    """计算各片区供需差额和总体瓶颈。"""

    # 把每个片区的供水量减去需求量，得到供需余额。
    # 先按用户站点范围过滤，避免有限站点账号看到其他片区数据。
    visible_areas = [area for area in data_source.supply.list() if user_has_station_access(user, area["station_id"])]
    # 根据供水量减需求量计算每个片区的供需结余。
    rows = [SupplyArea(**area, balance=area["supply"] - area["demand"]) for area in visible_areas]
    # 汇总所有片区，得到全局供需结果。
    # 汇总当前账号可见片区的总供水量、总需求量和总缺口。
    total_supply = sum(area.supply for area in rows)
    total_demand = sum(area.demand for area in rows)
    total_balance = total_supply - total_demand
    # 余额最小的片区作为当前模拟瓶颈。
    # 结余最小的片区作为当前 Mock 数据中的瓶颈；无授权数据时不调用 min。
    bottleneck = min(rows, key=lambda area: area.balance) if rows else None
    # from/to 未填写时使用固定演示时段；当前 Mock 数据不按时间重新计算。
    return SupplyBalanceResponse(
        from_time=from_time or "2026-10-15T00:00:00Z",
        to_time=to_time or "2026-10-15T23:59:59Z",
        areas=rows,
        total_supply=total_supply,
        total_demand=total_demand,
        total_balance=total_balance,
        bottleneck_summary=(
            f"{bottleneck.area} 当前供需缺口 {abs(bottleneck.balance):.0f} m³/d。"
            if bottleneck
            else "当前账号没有授权的供需站点。"
        ),
    )
