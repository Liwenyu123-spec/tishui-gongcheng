"""方案比较路由。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import require_roles
from ..schemas.schemes import SchemeCompareRequest, SchemeCompareResponse

# 方案比较只生成分析结果，不向现场设备下发控制指令。
router = APIRouter(prefix="/api/v1", tags=["方案"])


@router.post("/schemes/compare", response_model=SchemeCompareResponse)
def compare_schemes(
    payload: SchemeCompareRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> SchemeCompareResponse:
    """按模拟能耗和时延指标比较多个方案。"""

    # 空方案没有可比较对象，直接返回参数错误。
    if not payload.schemes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个方案")

    # 将前端传入的灵活字典规范化为统一的比较字段，并填充缺省值。
    results = []
    for index, scheme in enumerate(payload.schemes, start=1):
        results.append(
            {
                "scheme_id": scheme.get("scheme_id", f"scheme-{index}"),
                "name": scheme.get("name", f"方案 {index}"),
                "supply": float(scheme.get("supply", 0)),
                "delay_minutes": float(scheme.get("delay_minutes", 0)),
                "energy": float(scheme.get("energy", 0)),
                "risk": scheme.get("risk", "medium"),
            }
        )

    # 先选能耗较低的方案，能耗相同时再比较预计时延。
    best = min(results, key=lambda item: (item["energy"], item["delay_minutes"]))
    return SchemeCompareResponse(
        comparison_id=f"compare-{uuid4().hex[:10]}",
        results=results,
        recommendation=f"建议优先复核{best['name']}，其模拟能耗指标最低。",
    )
