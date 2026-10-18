"""数据导入接口的请求结果模型。"""

from pydantic import BaseModel


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
