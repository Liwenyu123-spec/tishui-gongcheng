"""审计事件的响应模型。"""

from datetime import datetime

from pydantic import BaseModel


class AuditEvent(BaseModel):
    """用户、告警和审核变更产生的审计事件结构。"""

    # 审计事件的唯一标识，用于在日志中定位一次变更。
    id: str
    # 执行的动作名称，例如 create、update 或 acknowledge。
    action: str
    # 被操作资源的类型，例如 incident、notification 或 user。
    resource: str
    # 被操作资源的业务编号；部分系统级操作可能没有资源编号。
    resource_id: str | None = None
    # 记录执行操作的用户；Mock 阶段默认使用管理员账号。
    operator: str = "mock-admin"
    # 事件发生时间，供审计查询按时间排序。
    occurred_at: datetime
    # 面向审计人员的补充描述，默认没有额外说明。
    detail: str = ""
    # 数据来源标记；当前接口返回的是内存 Mock 数据。
    source: str = "mock"
