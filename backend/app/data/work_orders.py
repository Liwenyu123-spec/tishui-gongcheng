"""工单 Mock 存储；服务重启后会清空新增工单。"""

from ..schemas.work_orders import WorkOrderDraft


# 当前阶段使用进程内字典模拟工单表，后续持久化时替换为 Repository。
_WORK_ORDERS: dict[str, WorkOrderDraft] = {}
