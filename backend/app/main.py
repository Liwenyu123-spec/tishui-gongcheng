import csv
import io
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="提水工程供水调度平台 API",
    version="0.3.0-mock",
    description="模拟阶段后端接口。当前仅提供基础和登录认证能力。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "water-dispatch-backend"
    environment: str = "mock"
    timestamp: datetime


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    permissions: list[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LogoutResponse(BaseModel):
    success: bool = True
    message: str = "已退出登录"


class Station(BaseModel):
    id: str
    name: str
    sequence: int
    station_type: str
    status: str
    source: str = "mock"


class StationDetail(Station):
    location: str
    description: str
    metrics: list[str]


class TopologyNode(BaseModel):
    station_id: str
    name: str
    sequence: int


class TopologyEdge(BaseModel):
    source: str
    target: str
    direction: str = "downstream"


class TopologyResponse(BaseModel):
    version: str
    confirmed_at: datetime
    source: str = "mock"
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class TelemetryPoint(BaseModel):
    observed_at: datetime
    metric: str
    value: float
    unit: str
    source: str = "mock"
    quality: str = "good"
    is_stale: bool = False


class Alarm(BaseModel):
    id: str
    station_id: str
    station_name: str
    level: str
    metric: str
    value: float
    unit: str
    threshold: str
    status: str
    occurred_at: datetime
    relation: str | None = None
    source: str = "mock"


class AlarmDetail(Alarm):
    description: str
    suggested_action: str


class SupplyArea(BaseModel):
    area: str
    station_id: str
    supply: float
    demand: float
    balance: float
    unit: str = "m³/d"
    pressure: float
    risk: str
    source: str = "mock"


class SupplyBalanceResponse(BaseModel):
    from_time: str
    to_time: str
    areas: list[SupplyArea]
    total_supply: float
    total_demand: float
    total_balance: float
    bottleneck_summary: str
    source: str = "mock"


class CsvImportResponse(BaseModel):
    success: bool
    filename: str | None
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    errors: list[str]
    source: str = "mock"


class SchemeCompareRequest(BaseModel):
    schemes: list[dict]


class SchemeCompareResponse(BaseModel):
    comparison_id: str
    results: list[dict]
    recommendation: str
    source: str = "mock"


class ReviewCreateRequest(BaseModel):
    subject: str
    recommendation: str
    comment: str = ""


class Review(BaseModel):
    id: str
    subject: str
    recommendation: str
    comment: str
    status: str
    created_at: datetime
    updated_at: datetime
    source: str = "mock"


class ReportGenerateRequest(BaseModel):
    report_type: str = "daily"
    report_date: str | None = None


class Report(BaseModel):
    id: str
    report_type: str
    report_date: str
    status: str
    title: str
    summary: str
    created_at: datetime
    source: str = "mock"


class WorkOrderDraftRequest(BaseModel):
    title: str
    station_id: str | None = None
    issue: str
    suggested_action: str
    priority: str = "medium"


class WorkOrderDraft(BaseModel):
    id: str
    title: str
    station_id: str | None
    issue: str
    suggested_action: str
    priority: str
    status: str = "draft"
    created_at: datetime
    source: str = "mock"


_USERS = {
    "admin": {
        "password": "admin123",
        "id": "user-admin",
        "username": "admin",
        "display_name": "系统管理员",
        "role": "admin",
        "permissions": ["read", "ask", "submit_scheme", "review", "knowledge", "audit"],
    },
    "operator": {
        "password": "operator123",
        "id": "user-operator",
        "username": "operator",
        "display_name": "运行值班员",
        "role": "operator",
        "permissions": ["read", "ask", "submit_scheme"],
    },
}
_TOKENS = {"mock-token-admin": "admin", "mock-token-operator": "operator"}

_STATIONS = [
    {
        "id": "jq-01",
        "name": "集泉一站",
        "sequence": 1,
        "station_type": "取水泵站",
        "status": "running",
        "location": "集泉取水口",
        "description": "工程上游取水及一级提水站点。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pump-01",
        "name": "一泵站",
        "sequence": 2,
        "station_type": "加压泵站",
        "status": "running",
        "location": "输水干线 1+200",
        "description": "承担一级输水加压。",
        "metrics": ["flow", "pressure", "energy"],
    },
    {
        "id": "pump-02",
        "name": "二泵站",
        "sequence": 3,
        "station_type": "加压泵站",
        "status": "warning",
        "location": "输水干线 4+800",
        "description": "承担中段输水加压。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pump-03",
        "name": "三泵站",
        "sequence": 4,
        "station_type": "加压泵站",
        "status": "running",
        "location": "输水干线 8+600",
        "description": "承担中下游输水加压。",
        "metrics": ["flow", "pressure", "energy"],
    },
    {
        "id": "pump-04",
        "name": "四泵站",
        "sequence": 5,
        "station_type": "末端泵站",
        "status": "running",
        "location": "平定城区入口",
        "description": "承担末端供水调节。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pingding-inlet",
        "name": "平定侧入口",
        "sequence": 6,
        "station_type": "供水入口",
        "status": "running",
        "location": "平定城区",
        "description": "工程输水进入片区的入口节点。",
        "metrics": ["flow", "pressure"],
    },
]

_ALARMS = [
    {
        "id": "alarm-20261015-001",
        "station_id": "pump-02",
        "station_name": "二泵站",
        "level": "high",
        "metric": "flow",
        "value": 812.0,
        "unit": "m³/h",
        "threshold": ">= 1000",
        "status": "unconfirmed",
        "occurred_at": datetime(2026, 10, 15, 10, 42, tzinfo=timezone.utc),
        "relation": "关联下游片区压力下降",
        "description": "出水流量低于当前运行阈值。",
        "suggested_action": "核查泵组运行状态和下游压力数据。",
    },
    {
        "id": "alarm-20261015-002",
        "station_id": "pump-04",
        "station_name": "四泵站",
        "level": "medium",
        "metric": "current",
        "value": 68.0,
        "unit": "A",
        "threshold": "<= 60",
        "status": "unconfirmed",
        "occurred_at": datetime(2026, 10, 15, 10, 18, tzinfo=timezone.utc),
        "relation": None,
        "description": "2 号泵电流高于设定阈值。",
        "suggested_action": "核查电机负荷和设备运行记录。",
    },
    {
        "id": "alarm-20261015-003",
        "station_id": "pump-03",
        "station_name": "三泵站",
        "level": "low",
        "metric": "level",
        "value": 3.2,
        "unit": "m",
        "threshold": ">= 3.5",
        "status": "confirmed",
        "occurred_at": datetime(2026, 10, 15, 9, 56, tzinfo=timezone.utc),
        "relation": None,
        "description": "站内水位低于运行参考值。",
        "suggested_action": "持续观察水位趋势和来水情况。",
    },
]

_SUPPLY_AREAS = [
    {"area": "平定城区", "station_id": "pump-04", "supply": 9200.0, "demand": 9800.0, "pressure": 0.38, "risk": "medium"},
    {"area": "东部片区", "station_id": "pump-03", "supply": 5600.0, "demand": 5200.0, "pressure": 0.43, "risk": "low"},
    {"area": "西部片区", "station_id": "pump-02", "supply": 4100.0, "demand": 4700.0, "pressure": 0.31, "risk": "high"},
]
_REVIEWS: dict[str, Review] = {}
_REPORTS: dict[str, Report] = {}


def _public_user(username: str) -> UserResponse:
    user = _USERS[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


def _get_current_username(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = _TOKENS.get(authorization[7:].strip())
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


@app.get("/api/v1/health", response_model=HealthResponse, tags=["基础"])
def health() -> HealthResponse:
    return HealthResponse(timestamp=datetime.now(timezone.utc))


@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["认证"])
def login(payload: LoginRequest) -> LoginResponse:
    user = _USERS.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return LoginResponse(access_token=f"mock-token-{payload.username}", user=_public_user(payload.username))


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["认证"])
def me(username: Annotated[str, Depends(_get_current_username)]) -> UserResponse:
    return _public_user(username)


@app.post("/api/v1/auth/logout", response_model=LogoutResponse, tags=["认证"])
def logout(_: Annotated[str, Depends(_get_current_username)]) -> LogoutResponse:
    return LogoutResponse()


@app.get("/api/v1/topology", response_model=TopologyResponse, tags=["拓扑"])
def topology() -> TopologyResponse:
    nodes = [TopologyNode(station_id=s["id"], name=s["name"], sequence=s["sequence"]) for s in _STATIONS]
    edges = [
        TopologyEdge(source=_STATIONS[index]["id"], target=_STATIONS[index + 1]["id"])
        for index in range(len(_STATIONS) - 1)
    ]
    return TopologyResponse(
        version="mock-topology-v1",
        confirmed_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        nodes=nodes,
        edges=edges,
    )


@app.get("/api/v1/stations", response_model=list[Station], tags=["站点"])
def stations() -> list[Station]:
    return [Station(**station) for station in _STATIONS]


@app.get("/api/v1/stations/{station_id}", response_model=StationDetail, tags=["站点"])
def station_detail(station_id: str) -> StationDetail:
    station = next((item for item in _STATIONS if item["id"] == station_id), None)
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return StationDetail(**station)


@app.get("/api/v1/stations/{station_id}/telemetry", response_model=list[TelemetryPoint], tags=["监控"])
def telemetry(
    station_id: str,
    metric: str | None = Query(default=None, max_length=32),
    from_time: str | None = Query(default=None, alias="from", max_length=64),
    to_time: str | None = Query(default=None, alias="to", max_length=64),
) -> list[TelemetryPoint]:
    if not any(station["id"] == station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")

    base_time = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    values = {
        "flow": (1120.0, "m³/h"),
        "pressure": (0.72, "MPa"),
        "level": (3.7, "m"),
        "energy": (184.0, "kWh"),
    }
    metrics = [metric] if metric else list(values)
    points: list[TelemetryPoint] = []
    for offset in range(6):
        for metric_name in metrics:
            value_unit = values.get(metric_name)
            if value_unit is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的测点: {metric_name}")
            value, unit = value_unit
            points.append(
                TelemetryPoint(
                    observed_at=base_time - timedelta(minutes=offset * 10),
                    metric=metric_name,
                    value=round(value + offset * 2, 3),
                    unit=unit,
                )
            )
    return points


@app.get("/api/v1/alarms", response_model=list[Alarm], tags=["告警"])
def alarms(
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    station_id: str | None = Query(default=None, max_length=64),
) -> list[Alarm]:
    rows = _ALARMS
    if status_filter:
        rows = [alarm for alarm in rows if alarm["status"] == status_filter]
    if station_id:
        rows = [alarm for alarm in rows if alarm["station_id"] == station_id]
    return [Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}}) for alarm in rows]


@app.get("/api/v1/alarms/{alarm_id}", response_model=AlarmDetail, tags=["告警"])
def alarm_detail(alarm_id: str) -> AlarmDetail:
    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    return AlarmDetail(**alarm)


@app.get("/api/v1/supply/balance", response_model=SupplyBalanceResponse, tags=["供需"])
def supply_balance(
    from_time: str | None = Query(default=None, alias="from", max_length=64),
    to_time: str | None = Query(default=None, alias="to", max_length=64),
) -> SupplyBalanceResponse:
    rows = [SupplyArea(**area, balance=area["supply"] - area["demand"]) for area in _SUPPLY_AREAS]
    total_supply = sum(area.supply for area in rows)
    total_demand = sum(area.demand for area in rows)
    total_balance = total_supply - total_demand
    bottleneck = min(rows, key=lambda area: area.balance)
    return SupplyBalanceResponse(
        from_time=from_time or "2026-10-15T00:00:00Z",
        to_time=to_time or "2026-10-15T23:59:59Z",
        areas=rows,
        total_supply=total_supply,
        total_demand=total_demand,
        total_balance=total_balance,
        bottleneck_summary=f"{bottleneck.area} 当前供需缺口 {abs(bottleneck.balance):.0f} m³/d。",
    )


@app.post("/api/v1/imports/telemetry-csv", response_model=CsvImportResponse, tags=["数据导入"])
async def import_telemetry_csv(request: Request) -> CsvImportResponse:
    filename = request.headers.get("x-filename")
    raw = await request.body()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=["CSV 必须使用 UTF-8 编码"])

    reader = csv.DictReader(io.StringIO(text))
    required = {"station_id", "observed_at", "metric", "value", "unit"}
    headers = set(reader.fieldnames or [])
    missing = sorted(required - headers)
    if missing:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=[f"缺少字段: {', '.join(missing)}"])

    errors: list[str] = []
    accepted = 0
    total = 0
    station_ids = {station["id"] for station in _STATIONS}
    for line_number, row in enumerate(reader, start=2):
        total += 1
        if row.get("station_id") not in station_ids:
            errors.append(f"第 {line_number} 行站点不存在: {row.get('station_id')}")
            continue
        try:
            float(row.get("value", ""))
            datetime.fromisoformat(row.get("observed_at", "").replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"第 {line_number} 行时间或数值格式错误")
            continue
        if not row.get("metric") or not row.get("unit"):
            errors.append(f"第 {line_number} 行测点或单位为空")
            continue
        accepted += 1
    return CsvImportResponse(
        success=not errors,
        filename=filename,
        total_rows=total,
        accepted_rows=accepted,
        rejected_rows=total - accepted,
        errors=errors,
    )


@app.post("/api/v1/schemes/compare", response_model=SchemeCompareResponse, tags=["方案"])
def compare_schemes(payload: SchemeCompareRequest) -> SchemeCompareResponse:
    if not payload.schemes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个方案")
    results = []
    for index, scheme in enumerate(payload.schemes, start=1):
        results.append(
            {
                "scheme_id": scheme.get("scheme_id", f"scheme-{index}"),
                "name": scheme.get("name", f"方案 {index}"),
                "supply": float(scheme.get("supply", 0)),
                "delay_minutes": float(scheme.get("delay_minutes", 0)),
                "energy": float(scheme.get("energy", 0)),
                "risk": scheme.get("risk", "medium"),
            }
        )
    best = min(results, key=lambda item: (item["energy"], item["delay_minutes"]))
    return SchemeCompareResponse(
        comparison_id=f"compare-{uuid4().hex[:10]}",
        results=results,
        recommendation=f"建议优先复核{best['name']}，其模拟能耗指标最低。",
    )


@app.post("/api/v1/reviews", response_model=Review, tags=["审核"])
def create_review(payload: ReviewCreateRequest) -> Review:
    now = datetime.now(timezone.utc)
    review = Review(id=f"review-{uuid4().hex[:10]}", **payload.model_dump(), status="pending", created_at=now, updated_at=now)
    _REVIEWS[review.id] = review
    return review


@app.get("/api/v1/reviews", response_model=list[Review], tags=["审核"])
def list_reviews() -> list[Review]:
    return list(_REVIEWS.values())


@app.get("/api/v1/reviews/{review_id}", response_model=Review, tags=["审核"])
def get_review(review_id: str) -> Review:
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    return review


@app.post("/api/v1/reports/generate", response_model=Report, tags=["报告"])
def generate_report(payload: ReportGenerateRequest) -> Report:
    now = datetime.now(timezone.utc)
    report = Report(
        id=f"report-{uuid4().hex[:10]}",
        report_type=payload.report_type,
        report_date=payload.report_date or now.date().isoformat(),
        status="draft",
        title=f"{payload.report_type}运行报告",
        summary="报告已根据当前模拟监控和供需数据生成草稿，需人工复核。",
        created_at=now,
    )
    _REPORTS[report.id] = report
    return report


@app.get("/api/v1/reports/{report_id}", response_model=Report, tags=["报告"])
def get_report(report_id: str) -> Report:
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


@app.post("/api/v1/work-orders/draft", response_model=WorkOrderDraft, tags=["工单"])
def create_work_order_draft(payload: WorkOrderDraftRequest) -> WorkOrderDraft:
    if payload.station_id and not any(station["id"] == payload.station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return WorkOrderDraft(id=f"work-order-{uuid4().hex[:10]}", **payload.model_dump(), created_at=datetime.now(timezone.utc))
