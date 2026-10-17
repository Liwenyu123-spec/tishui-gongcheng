"""知识库接口的请求和响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class KnowledgeImportRequest(BaseModel):
    """导入知识文档时提交的元数据和正文。"""

    # 上传文件的原始文件名。
    filename: str
    # 在知识库页面展示的文档标题。
    title: str
    # 文档版本号，未填写时使用 1.0。
    version: str = "1.0"
    # 导入的正文内容，Mock 阶段直接保存在内存中。
    content: str


class KnowledgeStatusUpdateRequest(BaseModel):
    """更新知识文档生命周期状态的请求。"""

    # valid 表示现行可用，pending 表示待审核，revoked 表示废止。
    status: Literal["valid", "pending", "revoked"]


class KnowledgeDocument(BaseModel):
    """知识文档列表中的元数据；正文当前不对外返回。"""

    # 知识文档的唯一编号。
    id: str
    # 原始文件名，便于下载或追溯来源。
    filename: str
    # 文档展示标题。
    title: str
    # 当前文档版本。
    version: str
    # 文档状态，默认表示可以使用。
    status: str = "valid"
    # 正文字符长度，列表接口不直接返回正文。
    content_length: int
    # 文档导入时间。
    imported_at: datetime
    # 数据来源标记。
    source: str = "mock"
