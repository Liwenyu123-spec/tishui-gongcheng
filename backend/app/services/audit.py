"""审计事件写入服务。"""

from datetime import datetime, timezone
from uuid import uuid4

from ..data.repositories import get_data_source, save_row
from ..schemas.audit import AuditEvent


data_source = get_data_source()


def record_audit(action: str, resource: str, resource_id: str | None, detail: str, operator: str = "mock-admin") -> None:
    """写入一条内存审计事件，供审计查询接口读取。"""

    # 使用短 UUID 生成本次操作的审计编号，避免依赖业务对象编号。
    audit_id = f"audit-{uuid4().hex[:10]}"
    # 记录 UTC 时间，便于和事件、通知、审核等其他时间字段对齐。
    occurred_at = datetime.now(timezone.utc)
    # 将完整审计模型追加到内存列表，查询接口会按倒序返回。
    data_source.audit.append(
        AuditEvent(
            id=audit_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            operator=operator,
            occurred_at=occurred_at,
            detail=detail,
        )
    )
    # 只把刚追加的这一条写入数据库，不再等请求结束时重写全部审计。
    save_row("commit_audit", data_source.audit.all()[-1])
