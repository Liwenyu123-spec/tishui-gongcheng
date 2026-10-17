"""报告接口的请求和响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReportGenerateRequest(BaseModel):
    """报告生成请求，默认生成日报。"""

    # 报告类型，默认生成日报。
    report_type: str = "daily"
    # 报告日期；为空时由服务端使用当前业务日期。
    report_date: str | None = None


class ReportStatusUpdateRequest(BaseModel):
    """更新报告草稿生命周期状态的请求。"""

    # draft 为待复核，reviewed 为已复核，archived 为已归档。
    status: Literal["draft", "reviewed", "archived"]


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
    # 报告草稿创建时间。
    created_at: datetime
    # 数据来源标记。
    source: str = "mock"
