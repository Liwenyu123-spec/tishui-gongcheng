"""模拟阶段的 FastAPI 后端入口。

应用初始化和暂未拆分的数据导入路由保留在这里；认证、健康检查、监控、供需、
方案、审核、报告、工单、用户和知识库模块已按领域拆到独立包。
"""

# csv 用于解析上传的遥测 CSV 文本。
import csv
# io 用于把请求中的字符串包装成 csv.DictReader 可以读取的文件对象。
import io
# datetime 用于校验导入 CSV 中的时间字段。
from datetime import datetime
# FastAPI 核心对象、异常、原始请求和状态码。
from fastapi import Depends, FastAPI, HTTPException, Request, status
# CORS 允许本地 Vue 前端从 5173 端口访问 8000 端口的后端。
from fastapi.middleware.cors import CORSMiddleware
# Pydantic 用于校验请求体和约束响应结构。
from pydantic import BaseModel

from .data.monitoring import _ALARMS, _STATIONS
from .dependencies import require_roles, user_has_station_access
from .data.audit import _AUDIT_EVENTS
from .routers.auth import router as auth_router
from .routers.health import router as health_router
from .routers.incidents import router as incidents_router
from .routers.monitoring import router as monitoring_router
from .routers.reports import router as reports_router
from .routers.reviews import router as reviews_router
from .routers.schemes import router as schemes_router
from .routers.supply import router as supply_router
from .routers.work_orders import router as work_orders_router
from .routers.users import router as users_router
from .routers.knowledge import router as knowledge_router
from .schemas.audit import AuditEvent
from .schemas.monitoring import Alarm
from .services.audit import record_audit as _record_audit

# 创建 FastAPI 应用对象；Swagger 文档会读取这里的元数据。
app = FastAPI(
    # Swagger 页面显示的项目名称。
    title="提水工程供水调度平台 API",
    # 当前模拟阶段的后端版本。
    version="0.3.0-mock",
    # Swagger 页面显示的项目说明。
    description="模拟阶段后端接口。当前使用内存 Mock 数据，供前后端联调。",
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

# 已完成拆分的领域路由在应用入口统一注册。
# 按业务领域注册已经拆分的路由模块，保持统一的 /api/v1 前缀。
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(incidents_router)
app.include_router(monitoring_router)
app.include_router(supply_router)
app.include_router(schemes_router)
app.include_router(reviews_router)
app.include_router(reports_router)
app.include_router(work_orders_router)
app.include_router(users_router)
app.include_router(knowledge_router)


# CSV 导入只返回校验统计，不写入数据库。
class CsvImportResponse(BaseModel):
    """遥测 CSV 校验接口返回的统计结果。"""

    # 整个文件是否没有发现任何校验错误。
    success: bool
    # 请求头中的原始文件名；未提供时为空。
    filename: str | None
    # CSV 中读取到的数据行总数，不包含表头。
    total_rows: int
    # 通过站点、时间、数值和测点字段校验的行数。
    accepted_rows: int
    # 未通过校验的行数。
    rejected_rows: int
    # 每条校验失败原因，包含对应的 CSV 行号。
    errors: list[str]
    # 数据来源标记，当前只做内存 Mock 校验。
    source: str = "mock"


# ------------------------- Mock 数据 -------------------------
# 以下字典/列表模拟数据库表，服务重启后会清空新增数据。
# POST /alarms/{alarm_id}/ack：确认指定告警并记录审计事件。
@app.post("/api/v1/alarms/{alarm_id}/ack", response_model=Alarm, tags=["告警"])
def acknowledge_alarm(alarm_id: str, user: dict = Depends(require_roles("admin", "operator"))) -> Alarm:
    """确认告警；监控查询路由已迁移到 routers.monitoring。"""
    # 根据告警编号查找记录；不存在时返回 404。
    alarm = next((item for item in _ALARMS if item["id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    # 告警确认还需要校验当前账号是否有权处理所属站点。
    if not user_has_station_access(user, alarm["station_id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权确认该站点告警")
    # Mock 阶段直接更新内存状态，并记录审计事件。
    alarm["status"] = "confirmed"
    _record_audit("acknowledge", "alarm", alarm_id, f"确认告警：{alarm['station_name']} {alarm['metric']}")
    return Alarm(**{key: value for key, value in alarm.items() if key not in {"description", "suggested_action"}})

# POST /imports/telemetry-csv：读取 CSV 原文并执行格式校验，不落库。
@app.post("/api/v1/imports/telemetry-csv", response_model=CsvImportResponse, tags=["数据导入"])
async def import_telemetry_csv(request: Request, _: dict = Depends(require_roles("admin", "operator"))) -> CsvImportResponse:
    """读取遥测 CSV 并返回格式校验统计，不写入遥测存储。"""

    # 文件名通过自定义请求头传入，当前不使用 multipart 以减少依赖。
    # 请求正文仍按原始 CSV 字节读取，便于保留 UTF-8 BOM 检测能力。
    filename = request.headers.get("x-filename")
    # 读取请求体中的 CSV 原始字节。
    raw = await request.body()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=["CSV 必须使用 UTF-8 编码"])

    # DictReader 将每行转为“字段名 -> 单元格值”，便于逐行校验。
    reader = csv.DictReader(io.StringIO(text))
    # 定义首期导入必须存在的字段。
    required = {"station_id", "observed_at", "metric", "value", "unit"}
    headers = set(reader.fieldnames or [])
    # 先检查表头完整性，缺字段时无需继续处理数据行。
    missing = sorted(required - headers)
    if missing:
        return CsvImportResponse(success=False, filename=filename, total_rows=0, accepted_rows=0, rejected_rows=0, errors=[f"缺少字段: {', '.join(missing)}"])

    errors: list[str] = []
    accepted = 0
    total = 0
    station_ids = {station["id"] for station in _STATIONS}
    # 从第二行开始计数，因为第一行已经是 CSV 表头。
    for line_number, row in enumerate(reader, start=2):
        total += 1
        if row.get("station_id") not in station_ids:
            errors.append(f"第 {line_number} 行站点不存在: {row.get('station_id')}")
            continue
        # 数值和时间字段必须能转换成功，否则记录该行错误并继续校验后续行。
        try:
            float(row.get("value", ""))
            datetime.fromisoformat(row.get("observed_at", "").replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"第 {line_number} 行时间或数值格式错误")
            continue
        # 测点名称和单位为空时，数据无法进入后续分析。
        if not row.get("metric") or not row.get("unit"):
            errors.append(f"第 {line_number} 行测点或单位为空")
            continue
        accepted += 1
    # 只有全部数据行通过校验时 success 才为 True；本接口不保存通过的数据。
    return CsvImportResponse(
        success=not errors,
        filename=filename,
        total_rows=total,
        accepted_rows=accepted,
        rejected_rows=total - accepted,
        errors=errors,
    )


# GET /audit-events：倒序返回最近的审计事件。
@app.get("/api/v1/audit-events", response_model=list[AuditEvent], tags=["管理"])
def audit_events(_: dict = Depends(require_roles("admin"))) -> list[AuditEvent]:
    """返回管理员可见的审计事件，并将最新事件放在前面。"""

    # 审计接口仅管理员可访问，并按时间倒序返回最近记录。
    return list(reversed(_AUDIT_EVENTS))
