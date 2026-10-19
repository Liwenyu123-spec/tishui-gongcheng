"""报告接口的请求和响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    """报告生成请求，默认生成日报。"""

    # 报告类型，默认生成日报。
    report_type: str = "daily"
    # 报告日期；为空时由服务端使用当前业务日期。
    report_date: str | None = None
    # 统计时间窗起点；未填写时使用报告日期当天 00:00:00 UTC。
    from_time: str | None = None
    # 统计时间窗终点；未填写时使用报告日期当天 23:59:59 UTC。
    to_time: str | None = None


class ReportStatusUpdateRequest(BaseModel):
    """更新报告草稿生命周期状态的请求。"""

    # draft 为待复核，reviewed 为已复核，archived 为已归档。
    status: Literal["draft", "reviewed", "archived"]


class ReportContentUpdateRequest(BaseModel):
    """报告草稿人工编辑请求；只允许修改标题和摘要。"""

    # 标题为空时保留原标题，提交非空字符串时替换当前标题。
    title: str | None = None
    # 摘要为空时保留原摘要，提交非空字符串时替换当前摘要。
    summary: str | None = None


class ReportMetric(BaseModel):
    """报告中的结构化指标，以及该指标对应的 Mock 来源编号。"""

    # 指标键用于前端稳定渲染和后续接入真实数据源。
    key: str
    # 面向调度人员显示的指标名称。
    label: str
    # 当前 Mock 阶段统一使用数值指标，单位单独保存。
    value: float
    unit: str = ""
    # 每个指标保留可回溯的供需片区或告警编号。
    source_ids: list[str] = Field(default_factory=list)


class Report(BaseModel):
    """报告草稿的响应结构。"""

    # 报告草稿唯一编号。
    id: str
    # 报告类型，例如 daily 或 weekly。
    report_type: str
    # 报告对应的业务日期。
    report_date: str
    # 报告当前状态，例如 draft 或 published。
    status: str
    # 报告标题。
    title: str
    # 报告摘要内容。
    summary: str
    # 报告统计时间窗起点。
    from_time: str = ""
    # 报告统计时间窗终点。
    to_time: str = ""
    # 生成报告时使用的数据版本标记。
    data_version: str = "mock-monitoring-v1"
    # 报告草稿创建时间。
    created_at: datetime
    # 数据来源标记。
    source: str = "mock"
    # 报告生成时汇总的结构化指标，便于页面展示和人工复核。
    metrics: list[ReportMetric] = Field(default_factory=list)
    # 本次报告涉及的全部来源编号，便于审计和后续替换真实数据源。
    source_ids: list[str] = Field(default_factory=list)
