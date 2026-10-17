"""审计事件的内存 Mock 数据。"""

from ..schemas.audit import AuditEvent


# 服务重启后会清空审计事件，当前仅供联调和页面展示。
# 列表顺序由查询接口反转，保证最新操作优先显示。
_AUDIT_EVENTS: list[AuditEvent] = []
