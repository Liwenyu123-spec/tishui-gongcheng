"""方案比较接口的请求和响应模型。"""

from pydantic import BaseModel


class SchemeCompareRequest(BaseModel):
    """方案比较请求；方案字段在模拟阶段允许灵活扩展。"""

    # 待比较的方案对象列表；每个对象可携带不同的业务指标。
    schemes: list[dict]


class SchemeCompareResponse(BaseModel):
    """方案比较结果和规则推荐。"""

    # 本次比较任务的唯一编号。
    comparison_id: str
    # 各方案的指标对比结果。
    results: list[dict]
    # 根据比较规则生成的推荐文字。
    recommendation: str
    # 数据来源标记。
    source: str = "mock"
