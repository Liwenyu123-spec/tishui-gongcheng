"""规则驱动 Agent 接口的请求和响应模型。

测点、告警和供需仍由只读规则整理。诊断中的规程说明可在配置密钥后
基于检索片段生成，不得编造实时数字或控制指令。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AgentIntent = Literal["status", "trend", "diagnosis", "supply", "control_rejected", "unknown"]


class AgentChatRequest(BaseModel):
    """Agent 问题请求。"""

    message: str = Field(min_length=1, max_length=2000)
    station_id: str | None = Field(default=None, max_length=64)


class AgentCitation(BaseModel):
    """回答使用的 Mock 数据或规程依据。"""

    source_type: Literal["telemetry", "alarm", "supply", "knowledge", "policy", "incident", "notification"]
    source_id: str
    title: str
    detail: str


class AgentWorkOrderSuggestion(BaseModel):
    """由诊断答案生成的工单草稿建议；只描述待人工确认的内容。"""

    # 建议关联的站点，便于后端再次执行站点权限校验。
    station_id: str
    # 面向调度人员显示的工单标题。
    title: str
    # 从告警和事件上下文整理出的待核查问题。
    issue: str
    # 现场人员需要人工核对的建议动作。
    suggested_action: str
    # 根据告警等级映射出的工单优先级。
    priority: Literal["low", "medium", "high"] = "medium"


class AgentAnswer(BaseModel):
    """规则分析返回的结构化答案。"""

    request_id: str
    intent: AgentIntent
    answer: str
    facts: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    citations: list[AgentCitation] = Field(default_factory=list)
    # 模型路由阶段提出的工具顺序；最终仍由后端白名单和意图规则校验。
    planned_tools: list[str] = Field(default_factory=list)
    # 只有诊断类答案提供工单建议，状态查询等答案保持为空。
    work_order_suggestion: AgentWorkOrderSuggestion | None = None
    # 诊断时基于检索片段整理的规程说明；无强相关命中时为空。
    protocol_explanation: str | None = None
    # 当前阶段所有结果均来自进程内 Mock 数据，不代表实时现场数据。
    data_quality: Literal["mock", "partial", "live", "stale"] = "mock"
    # 明确回答可用于什么范围，避免把联调结果当作生产结论。
    limitations: list[str] = Field(default_factory=lambda: ["当前结果来自 Mock 数据，仅用于联调和人工复核"])
    # 表示规则分析对当前结论的把握程度，不等同于真实生产准确率。
    confidence: Literal["low", "medium", "high"] = "medium"
    # 列出需要补充数据或人工现场确认的事项，避免把建议误认为已完成处置。
    pending_items: list[str] = Field(default_factory=list)
    # 标识本次规则分析覆盖的时间范围，避免把样本周期误认为实时结论。
    time_range: str = "当前 Mock 样本"
    # 事实数据的观测时间；没有对应测点时为空，不能用回答生成时间代替。
    observed_at: datetime | None = None
    # 观测数据的新鲜度与数据质量分开表示；没有观测时间时使用 unknown。
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    source: Literal["mock-rule", "llm-router+mock"] = "mock-rule"
    generated_at: datetime

