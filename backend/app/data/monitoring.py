"""拓扑、站点、遥测和告警共用的 Mock 数据。"""

from datetime import datetime, timezone


# 工程站点 Mock 数据；sequence 决定输水链路顺序。
# id 是接口和权限校验使用的稳定编号，metrics 是该站点支持的测点集合。
_STATIONS = [
    # 上游取水站，作为输水链路的起点。
    {"id": "jq-01", "name": "集泉一站", "sequence": 1, "station_type": "取水泵站", "status": "running", "location": "集泉取水口", "description": "工程上游取水及一级提水站点。", "metrics": ["flow", "pressure", "level", "energy"]},
    # 一级加压站，缺少水位测点示例。
    {"id": "pump-01", "name": "一泵站", "sequence": 2, "station_type": "加压泵站", "status": "running", "location": "输水干线 1+200", "description": "承担一级输水加压。", "metrics": ["flow", "pressure", "energy"]},
    # 二泵站用于 station-operator 站点范围权限测试。
    {"id": "pump-02", "name": "二泵站", "sequence": 3, "station_type": "加压泵站", "status": "warning", "location": "输水干线 4+800", "description": "承担中段输水加压。", "metrics": ["flow", "pressure", "level", "energy"]},
    # 中下游加压站，提供流量、压力和能耗测点。
    {"id": "pump-03", "name": "三泵站", "sequence": 4, "station_type": "加压泵站", "status": "running", "location": "输水干线 8+600", "description": "承担中下游输水加压。", "metrics": ["flow", "pressure", "energy"]},
    {"id": "pump-04", "name": "四泵站", "sequence": 5, "station_type": "末端泵站", "status": "running", "location": "平定城区入口", "description": "承担末端供水调节。", "metrics": ["flow", "pressure", "level", "energy"]},
    {"id": "pingding-inlet", "name": "平定侧入口", "sequence": 6, "station_type": "供水入口", "status": "running", "location": "平定城区", "description": "工程输水进入片区的入口节点。", "metrics": ["flow", "pressure"]},
]

# 告警 Mock 数据；详情字段不在列表接口中返回。
# level 表示严重程度，status 表示确认状态，occurred_at 使用 UTC 时间。
_ALARMS = [
    # 二泵站流量告警，用于演示高等级告警和下游关联关系。
    {"id": "alarm-20261015-001", "station_id": "pump-02", "station_name": "二泵站", "level": "high", "metric": "flow", "value": 812.0, "unit": "m³/h", "threshold": ">= 1000", "status": "unconfirmed", "occurred_at": datetime(2026, 10, 15, 10, 42, tzinfo=timezone.utc), "relation": "关联下游片区压力下降", "description": "出水流量低于当前运行阈值。", "suggested_action": "核查泵组运行状态和下游压力数据。"},
    # 四泵站电流告警，用于演示中等级别和无关联片区的情况。
    {"id": "alarm-20261015-002", "station_id": "pump-04", "station_name": "四泵站", "level": "medium", "metric": "current", "value": 68.0, "unit": "A", "threshold": "<= 60", "status": "unconfirmed", "occurred_at": datetime(2026, 10, 15, 10, 18, tzinfo=timezone.utc), "relation": None, "description": "2 号泵电流高于设定阈值。", "suggested_action": "核查电机负荷和设备运行记录。"},
    # 三泵站水位告警，初始状态设置为已确认。
    {"id": "alarm-20261015-003", "station_id": "pump-03", "station_name": "三泵站", "level": "low", "metric": "level", "value": 3.2, "unit": "m", "threshold": ">= 3.5", "status": "confirmed", "occurred_at": datetime(2026, 10, 15, 9, 56, tzinfo=timezone.utc), "relation": None, "description": "站内水位低于运行参考值。", "suggested_action": "持续观察水位趋势和来水情况。"},
]
