"""审核模块的内存 Mock 数据。"""

from ..schemas.reviews import Review


# 服务重启后会清空新增审核记录，后续接入数据库时替换此存储层。
# 审核状态由接口限制为 pending、approved、rejected 或 supplement 流程。
_REVIEWS: dict[str, Review] = {}
