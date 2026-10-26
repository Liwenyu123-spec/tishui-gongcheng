"""站点事件、通知、联系人和心跳的内存 Mock 数据。"""

from datetime import datetime

from ..schemas.incidents import Incident, Notification


# 首期只配置平台内通知；外部通知渠道需现场确认后再接入。
# 字典键是站点编号，列表内容是按优先级排列的主联系人账号。
_STATION_CONTACTS = {
    "jq-01": ["dispatch-admin"],
    "jq-02": ["dispatch-admin"],
    "pump-01": ["dispatch-admin"],
    "pump-02": ["dispatch-admin"],
    "pump-03": ["dispatch-admin"],
    "pump-04": ["dispatch-admin"],
    "sz-invert": ["dispatch-admin"],
    "pingding-inlet": ["dispatch-admin"],
}

# 首期使用固定的备用调度联系人模拟升级路由；真实联系人配置需经现场确认。
# 升级时原通知保留，另创建一条发送给备用联系人的通知。
_STATION_BACKUP_CONTACTS = {
    "jq-01": "dispatch-supervisor",
    "jq-02": "dispatch-supervisor",
    "pump-01": "dispatch-supervisor",
    "pump-02": "dispatch-supervisor",
    "pump-03": "dispatch-supervisor",
    "pump-04": "dispatch-supervisor",
    "sz-invert": "dispatch-supervisor",
    "pingding-inlet": "dispatch-supervisor",
}

# 服务重启后会清空事件和通知，后续接入数据库时替换此存储层。
# 事件以业务编号为键，通知以通知编号为键，便于按 ID 更新状态。
_INCIDENTS: dict[str, Incident] = {}
_NOTIFICATIONS: dict[str, Notification] = {}
# 记录每个站点最近一次心跳时间；服务重启后会清空。
# 心跳字典只保存最近一次 UTC 时间，不代表设备运行状态。
_STATION_HEARTBEATS: dict[str, datetime] = {}
