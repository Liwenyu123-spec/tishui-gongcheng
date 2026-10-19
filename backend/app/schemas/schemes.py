"""方案比较接口的请求和响应模型。"""

from pydantic import BaseModel, Field


class SchemeCompareRequest(BaseModel):
    """方案比较请求；方案字段保留灵活性，约束字段统一。"""

    # 待比较的方案对象列表；每个对象可携带不同的业务指标。
    schemes: list[dict]
    # 目标供水量；未填写时使用 13000 m³/d 的 Mock 目标。
    target_demand: float | None = None
    # 可选的时延、负荷和风险边界。
    constraints: dict = Field(default_factory=dict)


class SchemeCompareResponse(BaseModel):
    """方案比较结果和规则推荐。"""

    # 本次比较任务的唯一编号。
    comparison_id: str
    # 各方案的指标对比结果。
    results: list[dict]
    # 根据比较规则生成的推荐文字。
    recommendation: str
    # 推荐方案编号，供前端高亮和后续审核关联。
    recommended_scheme_id: str | None = None
    # 本次计算使用的目标、约束和假设。
    target_demand: float | None = None
    constraints: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    # 数据来源标记。
    source: str = "mock"
