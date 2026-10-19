"""方案比较路由。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import require_roles
from ..schemas.schemes import SchemeCompareRequest, SchemeCompareResponse
from ..services.scheme_analysis import compare_scheme_inputs

# 方案比较只生成分析结果，不向现场设备下发控制指令。
router = APIRouter(prefix="/api/v1", tags=["方案"])


@router.post("/schemes/compare", response_model=SchemeCompareResponse)
def compare_schemes(
    payload: SchemeCompareRequest,
    _: dict = Depends(require_roles("admin", "operator")),
) -> SchemeCompareResponse:
    """按供需、时延、能耗、负荷、风险和约束比较多个方案。"""

    # 空方案没有可比较对象，直接返回参数错误。
    if not payload.schemes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个方案")

    try:
        comparison = compare_scheme_inputs(
            payload.schemes,
            target_demand=payload.target_demand,
            constraints=payload.constraints,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return SchemeCompareResponse(
        comparison_id=f"compare-{uuid4().hex[:10]}",
        results=comparison["results"],
        recommendation=comparison["recommendation"],
        recommended_scheme_id=comparison["recommended_scheme_id"],
        target_demand=comparison["target_demand"],
        constraints=comparison["constraints"],
        assumptions=comparison["assumptions"],
    )
