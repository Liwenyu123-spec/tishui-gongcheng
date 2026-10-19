"""确定性的只读分析服务。

这里集中放置 Mock 遥测生成和趋势计算，避免 Agent 直接用告警等级代替趋势
分析。后续接入真实时序数据时，可以保留这些函数的返回结构，只替换数据读取层。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


_MOCK_TELEMETRY_AT = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TelemetrySample:
    """一条用于分析的只读遥测样本。"""

    station_id: str
    station_name: str
    metric: str
    value: float
    unit: str
    observed_at: datetime
    quality: str = "good"
    source: str = "mock"


_BASE_VALUES: dict[str, tuple[float, str]] = {
    "flow": (1120.0, "m³/h"),
    "pressure": (0.72, "MPa"),
    "level": (3.7, "m"),
    "energy": (184.0, "kWh"),
}

# 当前点在序列首位；后续点代表更早的观测。不同站点使用不同幅度，
# 这样“哪个站波动最大”是可复现的计算结果，不再由告警等级代替。
_VARIATION_PROFILE: dict[str, tuple[float, ...]] = {
    "flow": (0.0, -6.0, 8.0, -12.0, 10.0, -4.0),
    "pressure": (0.0, -0.008, 0.012, -0.018, 0.015, -0.006),
    "level": (0.0, -0.04, 0.06, -0.08, 0.05, -0.02),
    "energy": (0.0, 1.5, -1.0, 2.0, -0.5, 1.0),
}


def metric_label(metric: str) -> str:
    """返回面向调度人员的指标名称。"""

    return {"flow": "流量", "pressure": "压力", "level": "水位", "energy": "能耗"}.get(metric, metric)


def telemetry_series(station: dict, metric: str) -> list[TelemetrySample]:
    """按站点和指标生成六个固定 Mock 遥测点。"""

    if metric not in _BASE_VALUES:
        return []
    base, unit = _BASE_VALUES[metric]
    sequence = int(station.get("sequence", 1))
    # 站点间的基线偏移用于模拟逐级输水的差异。
    if metric == "flow":
        station_offset = -(sequence - 1) * 18.0
    elif metric == "pressure":
        station_offset = -(sequence - 1) * 0.02
    elif metric == "level":
        station_offset = -(sequence - 1) * 0.08
    else:
        station_offset = (sequence - 1) * 2.5

    profile = _VARIATION_PROFILE[metric]
    # 末端站点波动幅度更大，用于验证跨站点比较逻辑。
    scale = 1.0 + (sequence - 1) * 0.3
    return [
        TelemetrySample(
            station_id=station["id"],
            station_name=station["name"],
            metric=metric,
            value=round(base + station_offset + delta * scale, 3),
            unit=unit,
            observed_at=_MOCK_TELEMETRY_AT - timedelta(minutes=index * 10),
        )
        for index, delta in enumerate(profile)
    ]


def latest_telemetry(station: dict, metric: str) -> TelemetrySample | None:
    """返回指定站点指标的最新 Mock 样本。"""

    series = telemetry_series(station, metric)
    return series[0] if series else None


def compare_variation(stations: Iterable[dict], metric: str) -> list[dict]:
    """按最大值减最小值计算各站点波动，并按波动从高到低排序。"""

    results: list[dict] = []
    for station in stations:
        sample_series = telemetry_series(station, metric)
        if not sample_series:
            continue
        values = [sample.value for sample in sample_series]
        latest = sample_series[0]
        results.append(
            {
                "station_id": station["id"],
                "station_name": station["name"],
                "metric": metric,
                "unit": latest.unit,
                "latest": latest.value,
                "minimum": min(values),
                "maximum": max(values),
                "variation": round(max(values) - min(values), 3),
                "observed_at": latest.observed_at,
            }
        )
    return sorted(results, key=lambda item: (-item["variation"], item["station_id"]))
