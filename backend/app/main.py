"""模拟阶段的 FastAPI 后端入口。

应用初始化和暂未拆分的业务路由保留在这里；认证、健康检查和基础共享模块
已按领域拆到独立包，后续路由继续按相同方式迁移。
"""

# csv 用于解析上传的遥测 CSV 文本。
import csv
# io 用于把请求中的字符串包装成 csv.DictReader 可以读取的文件对象。
import io
# uuid4 用于生成 Mock 记录的唯一 ID。
from uuid import uuid4
# datetime 处理时间；timedelta 生成遥测时间序列；timezone 统一使用 UTC。
from datetime import datetime, timedelta, timezone
# Literal 约束审核状态的允许值。
from typing import Literal

# FastAPI 核心对象、异常、查询参数、原始请求和状态码。
from fastapi import FastAPI, HTTPException, Query, Request, status
# CORS 允许本地 Vue 前端从 5173 端口访问 8000 端口的后端。
from fastapi.middleware.cors import CORSMiddleware
# Pydantic 用于校验请求体和约束响应结构。
from pydantic import BaseModel

from .data.users import _USERS
from .routers.auth import router as auth_router
from .routers.health import router as health_router
from .schemas.auth import UserResponse

# 创建 FastAPI 应用对象；Swagger 文档会读取这里的元数据。
app = FastAPI(
    # Swagger 页面显示的项目名称。
    title="提水工程供水调度平台 API",
    # 当前模拟阶段的后端版本。
    version="0.3.0-mock",
    # Swagger 页面显示的项目说明。
    description="模拟阶段后端接口。当前仅提供基础和登录认证能力。",
)

# 注册跨域中间件，使 Vue 开发服务器可以请求本地后端。
app.add_middleware(
    CORSMiddleware,
    # 只允许当前前端开发地址访问。
    allow_origins=["http://localhost:5173"],
    # 允许浏览器携带认证信息。
    allow_credentials=True,
    # Mock 阶段允许常见 HTTP 方法。
    allow_methods=["*"],
    # Mock 阶段允许所有请求头，便于发送 Authorization。
    allow_headers=["*"],
)

# 基础和认证路由已按领域拆到独立模块。
app.include_router(health_router)
app.include_router(auth_router)


# 站点列表中的基础字段。
class Station(BaseModel):
    id: str
    name: str
    sequence: int
    station_type: str
    status: str
    source: str = "mock"


# 站点详情继承基础站点字段，并增加位置和测点信息。
class StationDetail(Station):
    location: str
    description: str
    metrics: list[str]


# 拓扑图中的节点，使用 station_id 关联站点。
class TopologyNode(BaseModel):
    station_id: str
    name: str
    sequence: int


# 拓扑图中的有向连接边。
class TopologyEdge(BaseModel):
    source: str
    target: str
    direction: str = "downstream"


# 拓扑接口的整体响应。
class TopologyResponse(BaseModel):
    version: str
    confirmed_at: datetime
    source: str = "mock"
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


# 单条遥测记录，包含值、单位、来源和质量状态。
class TelemetryPoint(BaseModel):
    observed_at: datetime
    metric: str
    value: float
    unit: str
    source: str = "mock"
    quality: str = "good"
    is_stale: bool = False


# 告警列表需要展示的字段。
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


# 告警详情在列表字段基础上增加说明和建议动作。
class AlarmDetail(Alarm):
    description: str
    suggested_action: str


# 告警确认响应复用告警列表字段，供前端刷新状态。


# 单个片区的供需计算结果。
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


# 供需平衡接口的整体响应。
class SupplyBalanceResponse(BaseModel):
    from_time: str
    to_time: str
    areas: list[SupplyArea]
    total_supply: float
    total_demand: float
    total_balance: float
    bottleneck_summary: str
    source: str = "mock"


# CSV 导入只返回校验统计，不写入数据库。
class CsvImportResponse(BaseModel):
    success: bool
    filename: str | None
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    errors: list[str]
    source: str = "mock"


# 方案比较请求；方案字段在模拟阶段允许灵活扩展。
class SchemeCompareRequest(BaseModel):
    schemes: list[dict]


# 方案比较结果和规则推荐。
class SchemeCompareResponse(BaseModel):
    comparison_id: str
    results: list[dict]
    recommendation: str
    source: str = "mock"


# 创建审核记录时提交的字段。
class ReviewCreateRequest(BaseModel):
    subject: str
    recommendation: str
    comment: str = ""


# 审核状态修改请求只允许通过、驳回或退回补充。
class ReviewUpdateRequest(BaseModel):
    status: Literal["approved", "rejected", "supplement"]
    comment: str | None = None


# 审核记录的存储和响应结构。
class Review(BaseModel):
    id: str
    subject: str
    recommendation: str
    comment: str
    status: str
    created_at: datetime
    updated_at: datetime
    source: str = "mock"


# 报告生成请求，默认生成日报。
class ReportGenerateRequest(BaseModel):
    report_type: str = "daily"
    report_date: str | None = None


# 报告草稿的响应结构。
class Report(BaseModel):
    id: str
    report_type: str
    report_date: str
    status: str
    title: str
    summary: str
    created_at: datetime
    source: str = "mock"


# 工单草稿请求；只描述建议，不触发设备操作。
class WorkOrderDraftRequest(BaseModel):
    title: str
    station_id: str | None = None
    issue: str
    suggested_action: str
    priority: str = "medium"


# 工单草稿响应结构。
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


# 新建用户请求。
class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "operator"
    permissions: list[str] = []


# 修改用户时允许提交的可选字段。
class UserPatchRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    permissions: list[str] | None = None


# 导入知识文档时提交的元数据和正文。
class KnowledgeImportRequest(BaseModel):
    filename: str
    title: str
    version: str = "1.0"
    content: str


# 知识文档列表中的元数据；正文当前不对外返回。
class KnowledgeDocument(BaseModel):
    id: str
    filename: str
    title: str
    version: str
    status: str = "valid"
    content_length: int
    imported_at: datetime
    source: str = "mock"


# 用户和文档变更产生的审计事件结构。
class AuditEvent(BaseModel):
    id: str
    action: str
    resource: str
    resource_id: str | None = None
    operator: str = "mock-admin"
    occurred_at: datetime
    detail: str = ""
    source: str = "mock"


# ------------------------- Mock 数据 -------------------------
# 工程站点 Mock 数据；sequence 决定输水链路顺序。
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

# 告警 Mock 数据；详情字段 description/suggested_action 不在列表接口中返回。
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

# 片区供需 Mock 数据；balance 由接口根据 supply-demand 计算。
_SUPPLY_AREAS = [
    {"area": "平定城区", "station_id": "pump-04", "supply": 9200.0, "demand": 9800.0, "pressure": 0.38, "risk": "medium"},
    {"area": "东部片区", "station_id": "pump-03", "supply": 5600.0, "demand": 5200.0, "pressure": 0.43, "risk": "low"},
    {"area": "西部片区", "station_id": "pump-02", "supply": 4100.0, "demand": 4700.0, "pressure": 0.31, "risk": "high"},
]
# 以下字典/列表模拟数据库表，服务重启后会清空新增数据。
_REVIEWS: dict[str, Review] = {}
_REPORTS: dict[str, Report] = {}
_KNOWLEDGE: dict[str, KnowledgeDocument] = {}
_AUDIT_EVENTS: list[AuditEvent] = []


# 将内部用户记录转换为不含 password 的公开响应。
def _public_user(username: str) -> UserResponse:
    user = _USERS[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


# 写入一条内存审计事件，供审计查询接口读取。
def _record_audit(action: str, resource: str, resource_id: str | None, detail: str) -> None:
    _AUDIT_EVENTS.append(
        AuditEvent(
            id=f"audit-{uuid4().hex[:10]}",
            action=action,
            resource=resource,
            resource_id=resource_id,
            occurred_at=datetime.now(timezone.utc),
            detail=detail,
        )
    )


# GET /topology：把站点列表转换为拓扑节点和相邻连接边。
@app.get("/api/v1/topology", response_model=TopologyResponse, tags=["拓扑"])
def topology() -> TopologyResponse:
    # 每个站点对应一个拓扑节点。
    nodes = [TopologyNode(station_id=s["id"], name=s["name"], sequence=s["sequence"]) for s in _STATIONS]
    # 按站点顺序把相邻节点连接起来，形成单向输水链路。
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


# GET /stations：返回全部站点的基础字段。
@app.get("/api/v1/stations", response_model=list[Station], tags=["站点"])
def stations() -> list[Station]:
    # Pydantic 会校验每条 Mock 字典并过滤出 Station 模型定义的字段。
    return [Station(**station) for station in _STATIONS]


# GET /stations/{station_id}：查询单个站点的详细资料。
@app.get("/api/v1/stations/{station_id}", response_model=StationDetail, tags=["站点"])
def station_detail(station_id: str) -> StationDetail:
    # 在 Mock 站点表中按 ID 查找目标站点。
    station = next((item for item in _STATIONS if item["id"] == station_id), None)
    # 找不到时明确返回 404。
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return StationDetail(**station)


# GET /stations/{station_id}/telemetry：生成指定站点的模拟时序数据。
@app.get("/api/v1/stations/{station_id}/telemetry", response_model=list[TelemetryPoint], tags=["监控"])
def telemetry(
    station_id: str,
    metric: str | None = Query(default=None, max_length=32),
    from_time: str | None = Query(default=None, alias="from", max_length=64),
    to_time: str | None = Query(default=None, alias="to", max_length=64),
) -> list[TelemetryPoint]:
    # 先确认站点存在，避免为未知站点返回看似有效的遥测。
    if not any(station["id"] == station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")

    # 模拟数据的最新时间点。
    base_time = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    # 每个测点的基准值和单位。
    values = {
        "flow": (1120.0, "m³/h"),
        "pressure": (0.72, "MPa"),
        "level": (3.7, "m"),
        "energy": (184.0, "kWh"),
    }
    # 指定 metric 时只返回一个测点，否则返回全部测点。
    metrics = [metric] if metric else list(values)
    # 用列表收集最终响应。
    points: list[TelemetryPoint] = []
    # 生成 6 个时间点，每个时间点间隔 10 分钟。
    for offset in range(6):
        for metric_name in metrics:
            # 读取当前测点的基准值和单位。
            value_unit = values.get(metric_name)
            if value_unit is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的测点: {metric_name}")
            # 拆开元组，并为不同时间点增加简单的模拟变化。
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


# GET /alarms：返回告警列表，可按 status 和 station_id 筛选。
@app.get("/api/v1/alarms", response_model=list[Alarm], tags=["告警"])
def alarms(
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    station_id: str | None = Query(default=None, max_length=64),
) -> list[Alarm]:
    # 先使用完整 Mock 告警列表作为查询源。
    rows = _ALARMS
    # 有状态参数时只保留匹配记录。
    if status_filter:
        rows = [alarm for alarm in rows if alarm["status"] == status_filter]
    if station_id:
        rows = [alarm for alarm in rows if alarm["station_id"] == station_id]
    return [Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}}) for alarm in rows]


# GET /alarms/{alarm_id}：返回单条告警及处理建议。
@app.get("/api/v1/alarms/{alarm_id}", response_model=AlarmDetail, tags=["告警"])
def alarm_detail(alarm_id: str) -> AlarmDetail:
    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    return AlarmDetail(**alarm)


# POST /alarms/{alarm_id}/ack：确认指定告警并记录审计事件。
@app.post("/api/v1/alarms/{alarm_id}/ack", response_model=Alarm, tags=["告警"])
def acknowledge_alarm(alarm_id: str) -> Alarm:
    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    alarm["status"] = "confirmed"
    _record_audit("acknowledge", "alarm", alarm_id, f"确认告警：{alarm['station_name']} {alarm['metric']}")
    return Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}})


# GET /supply/balance：计算各片区供需差额和总体瓶颈。
@app.get("/api/v1/supply/balance", response_model=SupplyBalanceResponse, tags=["供需"])
def supply_balance(
    from_time: str | None = Query(default=None, alias="from", max_length=64),
    to_time: str | None = Query(default=None, alias="to", max_length=64),
) -> SupplyBalanceResponse:
    # 把每个片区的供水量减去需求量，得到供需余额。
    rows = [SupplyArea(**area, balance=area["supply"] - area["demand"]) for area in _SUPPLY_AREAS]
    # 汇总所有片区，得到全局供需结果。
    total_supply = sum(area.supply for area in rows)
    total_demand = sum(area.demand for area in rows)
    total_balance = total_supply - total_demand
    # 余额最小的片区作为当前模拟瓶颈。
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


# POST /imports/telemetry-csv：读取 CSV 原文并执行格式校验，不落库。
@app.post("/api/v1/imports/telemetry-csv", response_model=CsvImportResponse, tags=["数据导入"])
async def import_telemetry_csv(request: Request) -> CsvImportResponse:
    # 文件名通过自定义请求头传入，当前不使用 multipart 以减少依赖。
    filename = request.headers.get("x-filename")
    # 读取请求体中的 CSV 原始字节。
    raw = await request.body()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=["CSV 必须使用 UTF-8 编码"])

    # DictReader 会把每行转换成“列名 → 值”的字典。
    reader = csv.DictReader(io.StringIO(text))
    # 定义首期导入必须存在的字段。
    required = {"station_id", "observed_at", "metric", "value", "unit"}
    headers = set(reader.fieldnames or [])
    missing = sorted(required - headers)
    if missing:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=[f"缺少字段: {', '.join(missing)}"])

    errors: list[str] = []
    accepted = 0
    total = 0
    station_ids = {station["id"] for station in _STATIONS}
    # 从第 2 行开始计数，因为第 1 行是表头。
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


# POST /schemes/compare：按模拟能耗和时延指标比较多个方案。
@app.post("/api/v1/schemes/compare", response_model=SchemeCompareResponse, tags=["方案"])
def compare_schemes(payload: SchemeCompareRequest) -> SchemeCompareResponse:
    if not payload.schemes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少提供一个方案")
    # 规范化每个方案的默认字段，生成统一的比较结果。
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
    # 先按能耗排序，再按时延排序，选出模拟推荐方案。
    best = min(results, key=lambda item: (item["energy"], item["delay_minutes"]))
    return SchemeCompareResponse(
        comparison_id=f"compare-{uuid4().hex[:10]}",
        results=results,
        recommendation=f"建议优先复核{best['name']}，其模拟能耗指标最低。",
    )


# POST /reviews：创建一条待人工处理的审核记录。
@app.post("/api/v1/reviews", response_model=Review, tags=["审核"])
def create_review(payload: ReviewCreateRequest) -> Review:
    now = datetime.now(timezone.utc)
    review = Review(id=f"review-{uuid4().hex[:10]}", **payload.model_dump(), status="pending", created_at=now, updated_at=now)
    _REVIEWS[review.id] = review
    return review


# GET /reviews：查询当前进程内的审核记录。
@app.get("/api/v1/reviews", response_model=list[Review], tags=["审核"])
def list_reviews() -> list[Review]:
    return list(_REVIEWS.values())


# GET /reviews/{review_id}：按 ID 查询审核详情。
@app.get("/api/v1/reviews/{review_id}", response_model=Review, tags=["审核"])
def get_review(review_id: str) -> Review:
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    return review


# PATCH /reviews/{review_id}：更新审核结论并写入审计事件。
@app.patch("/api/v1/reviews/{review_id}", response_model=Review, tags=["审核"])
def update_review(review_id: str, payload: ReviewUpdateRequest) -> Review:
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核记录不存在")
    if review.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该审核记录已处理")
    review.status = payload.status
    if payload.comment is not None:
        review.comment = payload.comment
    review.updated_at = datetime.now(timezone.utc)
    _record_audit(payload.status, "review", review_id, f"审核记录 {review.subject} 状态更新为 {payload.status}")
    return review


# POST /reports/generate：生成一份需要人工复核的报告草稿。
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


# GET /reports/{report_id}：按 ID 查询报告草稿。
@app.get("/api/v1/reports/{report_id}", response_model=Report, tags=["报告"])
def get_report(report_id: str) -> Report:
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


# POST /work-orders/draft：根据建议生成工单草稿，不执行现场控制。
@app.post("/api/v1/work-orders/draft", response_model=WorkOrderDraft, tags=["工单"])
def create_work_order_draft(payload: WorkOrderDraftRequest) -> WorkOrderDraft:
    if payload.station_id and not any(station["id"] == payload.station_id for station in _STATIONS):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return WorkOrderDraft(id=f"work-order-{uuid4().hex[:10]}", **payload.model_dump(), created_at=datetime.now(timezone.utc))


# GET /audit-events：倒序返回最近的审计事件。
@app.get("/api/v1/audit-events", response_model=list[AuditEvent], tags=["管理"])
def audit_events() -> list[AuditEvent]:
    return list(reversed(_AUDIT_EVENTS))


# GET /users：返回所有用户的公开信息，不返回密码。
@app.get("/api/v1/users", response_model=list[UserResponse], tags=["管理"])
def users() -> list[UserResponse]:
    return [_public_user(username) for username in _USERS]


# POST /users：创建一个内存 Mock 用户并记录审计事件。
@app.post("/api/v1/users", response_model=UserResponse, tags=["管理"])
def create_user(payload: UserCreateRequest) -> UserResponse:
    if payload.username in _USERS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    user_id = f"user-{uuid4().hex[:10]}"
    _USERS[payload.username] = {
        "password": payload.password,
        "id": user_id,
        "username": payload.username,
        "display_name": payload.display_name,
        "role": payload.role,
        "permissions": payload.permissions,
    }
    _record_audit("create", "user", user_id, f"创建用户 {payload.username}")
    return _public_user(payload.username)


# PATCH /users/{user_id}：只更新请求中实际提供的字段。
@app.patch("/api/v1/users/{user_id}", response_model=UserResponse, tags=["管理"])
def update_user(user_id: str, payload: UserPatchRequest) -> UserResponse:
    username = next((name for name, user in _USERS.items() if user["id"] == user_id), None)
    if username is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    updates = payload.model_dump(exclude_none=True)
    _USERS[username].update(updates)
    _record_audit("update", "user", user_id, f"修改用户 {username}")
    return _public_user(username)


# GET /knowledge：返回已导入知识文档的元数据。
@app.get("/api/v1/knowledge", response_model=list[KnowledgeDocument], tags=["知识库"])
def knowledge() -> list[KnowledgeDocument]:
    return list(_KNOWLEDGE.values())


# POST /knowledge/import：保存知识文档元数据并记录正文长度。
@app.post("/api/v1/knowledge/import", response_model=KnowledgeDocument, tags=["知识库"])
def import_knowledge(payload: KnowledgeImportRequest) -> KnowledgeDocument:
    document = KnowledgeDocument(
        id=f"knowledge-{uuid4().hex[:10]}",
        filename=payload.filename,
        title=payload.title,
        version=payload.version,
        content_length=len(payload.content),
        imported_at=datetime.now(timezone.utc),
    )
    _KNOWLEDGE[document.id] = document
    _record_audit("import", "knowledge", document.id, f"导入文档 {document.filename}")
    return document
