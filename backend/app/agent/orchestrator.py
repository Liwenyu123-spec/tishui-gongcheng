"""协调 Agent 的规则编排入口。

这里先保留确定性的编排边界：答案仍由现有规则服务生成，协调器只决定专业 Agent
和只读工具白名单。后续接入模型或 LangGraph 时，可以在此处替换计划生成逻辑。
"""

from .tools import AgentPlan, plan_for_intent
from ..schemas.agent import AgentAnswer


def coordinate(answer: AgentAnswer) -> AgentPlan:
    """根据已确定的意图生成一次最小专业协作计划。"""

    return plan_for_intent(answer.intent)

