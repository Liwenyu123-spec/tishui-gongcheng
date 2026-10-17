"""拓扑、站点、遥测和告警共用的 Mock 数据。"""

from datetime import datetime, timezone


# 工程站点 Mock 数据；sequence 决定输水链路顺序。
_STATIONS = [
    {"id": "jq-01", "name": "集泉一站", "sequence": 1, "station_type": "取水泵站", "status": "running", "location": "集泉取水口", "description": "工程上游取水及一级提水站点。", "metrics": ["flow", "pressure", "level", "energy"]},
    {"id": "pump-01", "name": "一泵站", "sequence": 2, "station_type": "加压泵站", "status": "running", "location": "输水干线 1+200", "description": "承担一级输水加压。", "metrics": ["flow", "pressure", "energy"]},
    {"id": "pump-02", "name": "二泵站", "sequence": 3, "station_type": "加压泵站", "status": "warning", "location": "输水干线 4+800", "description": "承担中段输水加压。", "metrics": ["flow", "pressure", "level", "energy"]},
    {"id": "pump-03", "name": "三泵站", "sequence": 4, "station_type": "加压泵站", "status": "running", "location": "输水干线 8+600", "description": "承担中下游输水加压。", "metrics": ["flow", "pressure", "energy"]},
    {"id": "pump-04", "name": "四泵站", "sequence": 5, "station_type": "末端泵站", "status": "running", "location": "平定城区入口", "description": "承担末端供水调节。", "metrics": ["flow", "pressure", "level", "energy"]},
    {"id": "pingding-inlet", "name": "平定侧入口", "sequence": 6, "station_type": "供水入口", "status": "running", "location": "平定城区", "description": "工程输水进入片区的入口节点。", "metrics": ["flow", "pressure"]},
]

# 告警 Mock 数据；详情字段不在列表接口中返回。
_ALARMS = [
    {"id": "alarm-20261015-001", "station_id": "pump-02", "station_name": "二泵站", "level": "high", "metric": "flow", "value": 812.0, "unit": "m³/h", "threshold": ">= 1000", "status": "unconfirmed", "occurred_at": datetime(2026, 10, 15, 10, 42, tzinfo=timezone.utc), "relation": "关联下游片区压力下降", "description": "出水流量低于当前运行阈值。", "suggested_action": "核查泵组运行状态和下游压力数据。"},
    {"id": "alarm-20261015-002", "station_id": "pump-04", "station_name": "四泵站", "level": "medium", "metric": "current", "value": 68.0, "unit": "A", "threshold": "<= 60", "status": "unconfirmed", "occurred_at": datetime(2026, 10, 15, 10, 18, tzinfo=timezone.utc), "relation": None, "description": "2 号泵电流高于设定阈值。", "suggested_action": "核查电机负荷和设备运行记录。"},
    {"id": "alarm-20261015-003", "station_id": "pump-03", "station_name": "三泵站", "level": "low", "metric": "level", "value": 3.2, "unit": "m", "threshold": ">= 3.5", "status": "confirmed", "occurred_at": datetime(2026, 10, 15, 9, 56, tzinfo=timezone.utc), "relation": None, "description": "站内水位低于运行参考值。", "suggested_action": "持续观察水位趋势和来水情况。"},
]
