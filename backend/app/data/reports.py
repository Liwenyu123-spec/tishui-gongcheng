"""报告模块的内存 Mock 数据。"""

from ..schemas.reports import Report


# 服务重启后会清空报告草稿，当前仅供联调和页面展示。
# 字典键为报告编号，值包含报告标题、摘要和人工复核状态。
_REPORTS: dict[str, Report] = {}
