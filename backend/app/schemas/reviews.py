"""审核接口的请求和响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReviewCreateRequest(BaseModel):
    """创建审核记录时提交的字段。"""

    # 待审核对象的名称或业务编号。
    subject: str
    # 系统或提交人给出的建议方案。
    recommendation: str
    # 审核人补充意见，默认为空。
    comment: str = ""


class ReviewUpdateRequest(BaseModel):
    """审核状态修改请求。"""

    # 审核结果，只允许通过、驳回或要求补充材料。
    status: Literal["approved", "rejected", "supplement"]
    # 审核状态变更时的说明，可不填写。
    comment: str | None = None


class Review(BaseModel):
    """审核记录的存储和响应结构。"""

    # 审核记录唯一编号。
    id: str
    # 被审核对象。
    subject: str
    # 审核建议。
    recommendation: str
    # 审核意见。
    comment: str
    # 当前审核状态。
    status: str
    # 审核记录创建时间。
    created_at: datetime
    # 审核记录最近更新时间。
    updated_at: datetime
    # 数据来源标记。
    source: str = "mock"
