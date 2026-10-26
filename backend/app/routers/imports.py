"""遥测文件导入和格式校验路由。"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles, user_has_station_access
from ..schemas.imports import CsvImportResponse

# 导入路由校验 CSV。全部通过后写入 telemetry_readings。
router = APIRouter(prefix="/api/v1", tags=["数据导入"])
data_source = get_data_source()


@router.post("/imports/telemetry-csv", response_model=CsvImportResponse)
async def import_telemetry_csv(
    request: Request,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> CsvImportResponse:
    """读取遥测 CSV。有错误时不写入；全部通过后写入数据库。"""

    # 文件名通过自定义请求头传入，当前不使用 multipart 以减少依赖。
    filename = request.headers.get("x-filename")
    # 读取请求体中的 CSV 原始字节，保留 UTF-8 BOM 检测能力。
    raw = await request.body()
    try:
        # utf-8-sig 同时兼容普通 UTF-8 和带 BOM 的 Excel 导出文件。
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # 编码不正确时无法继续按行解析，直接返回失败统计。
        return CsvImportResponse(
            success=False,
            filename=filename,
            total_rows=0,
            accepted_rows=0,
            rejected_rows=0,
            errors=["CSV 必须使用 UTF-8 编码"],
        )

    # DictReader 将每行转为“字段名 -> 单元格值”，便于逐行校验。
    reader = csv.DictReader(io.StringIO(text))
    # 定义首期导入必须存在的字段。
    required = {"station_id", "observed_at", "metric", "value", "unit"}
    headers = set(reader.fieldnames or [])
    # 先检查表头完整性，缺字段时无需继续处理数据行。
    missing = sorted(required - headers)
    if missing:
        return CsvImportResponse(
            success=False,
            filename=filename,
            total_rows=0,
            accepted_rows=0,
            rejected_rows=0,
            errors=[f"缺少字段: {', '.join(missing)}"],
        )

    errors: list[str] = []
    accepted_rows: list[dict] = []
    total = 0
    stations = {station["id"]: station for station in data_source.stations.list()}
    # 从第二行开始计数，因为第一行已经是 CSV 表头。
    for line_number, row in enumerate(reader, start=2):
        total += 1
        station = stations.get(row.get("station_id") or "")
        if station is None:
            errors.append(f"第 {line_number} 行站点不存在: {row.get('station_id')}")
            continue
        if not user_has_station_access(user, row["station_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"当前账号无权导入站点 {row['station_id']} 数据")
        metric = (row.get("metric") or "").strip()
        if metric not in station.get("metrics", []):
            errors.append(f"第 {line_number} 行站点不支持测点: {metric}")
            continue
        try:
            value = float(row.get("value", ""))
            observed_at = datetime.fromisoformat(row.get("observed_at", "").replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"第 {line_number} 行时间或数值格式错误")
            continue
        if not row.get("unit"):
            errors.append(f"第 {line_number} 行测点或单位为空")
            continue
        accepted_rows.append({"station_id": station["id"], "metric": metric, "value": value, "observed_at": observed_at})

    if not errors and accepted_rows:
        writer = getattr(data_source, "import_telemetry_rows", None)
        if writer is not None:
            writer(accepted_rows)

    return CsvImportResponse(
        success=not errors,
        filename=filename,
        total_rows=total,
        accepted_rows=len(accepted_rows),
        rejected_rows=total - len(accepted_rows),
        errors=errors,
    )
