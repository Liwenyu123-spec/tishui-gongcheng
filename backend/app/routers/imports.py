"""遥测文件导入和格式校验路由。"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles, user_has_station_access
from ..schemas.imports import CsvImportResponse

# 导入路由使用统一的接口前缀，当前只负责校验，不写入数据库。
router = APIRouter(prefix="/api/v1", tags=["数据导入"])
data_source = get_data_source()


@router.post("/imports/telemetry-csv", response_model=CsvImportResponse)
async def import_telemetry_csv(
    request: Request,
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> CsvImportResponse:
    """读取遥测 CSV 并返回格式校验统计，不写入遥测存储。"""

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
    accepted = 0
    total = 0
    # 站点编号来自当前 Mock 站点列表，不依赖数据库。
    station_ids = {station["id"] for station in data_source.stations.list()}
    # 从第二行开始计数，因为第一行已经是 CSV 表头。
    for line_number, row in enumerate(reader, start=2):
        total += 1
        # 站点不存在时拒绝当前行，但继续校验后续数据。
        if row.get("station_id") not in station_ids:
            errors.append(f"第 {line_number} 行站点不存在: {row.get('station_id')}")
            continue
        # 站点值班账号不能借 CSV 接口导入其他站点数据。
        if not user_has_station_access(user, row["station_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"当前账号无权导入站点 {row['station_id']} 数据")
        # 数值和时间字段必须能转换成功。
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
