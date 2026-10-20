"""知识库接口的请求和响应模型。"""

from datetime import datetime
from typing import Literal

KnowledgeCategory = Literal["规程", "手册", "台账", "维修记录", "应急预案"]

from pydantic import BaseModel, Field


class KnowledgeImportRequest(BaseModel):
    """导入知识文档时提交的元数据和正文。"""

    # 上传文件的原始文件名。
    filename: str
    # 在知识库页面展示的文档标题。
    title: str
    # 文档版本号，未填写时使用 1.0。
    version: str = "1.0"
    # 资料类别。同一标题和类别只允许一个现行版本。
    category: KnowledgeCategory = "规程"
    # 导入的正文内容，Mock 阶段直接保存在内存中。
    content: str
    # 适用站点；为空表示全局规程。
    station_ids: list[str] = Field(default_factory=list)
    # 文档有效时间窗口；为空表示不设置对应边界。
    effective_from: datetime | None = None
    effective_to: datetime | None = None


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
    # 规程、手册、台账、维修记录或应急预案。
    category: KnowledgeCategory = "规程"
    # 文档状态：pending 待审、valid 现行、revoked 废止。
    status: Literal["valid", "pending", "revoked"] = "pending"
    # 正文字符长度，列表接口不直接返回正文。
    content_length: int
    # 文档导入时间。
    imported_at: datetime
    # 适用站点；为空表示全局规程。
    station_ids: list[str] = Field(default_factory=list)
    # 文档生效和失效时间。
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    # 最近一次进入现行状态的时间。
    approved_at: datetime | None = None
    # 数据来源标记。
    source: str = "mock"


class KnowledgeSearchHit(BaseModel):
    """本地规程检索返回的引用片段。"""

    source_id: str
    title: str
    version: str
    detail: str
    score: int
    source: Literal["mock-rule", "mock-document", "chroma-document"] = "mock-rule"
    filename: str = ""
    station_ids: list[str] = Field(default_factory=list)
    chunk_index: int | None = None
    location: str = ""
    category: str = ""
    confidence: Literal["normal", "low"] = "normal"


class KnowledgeSearchResponse(BaseModel):
    """Agent 或知识库页面可以消费的检索结果。"""

    query: str
    results: list[KnowledgeSearchHit]
    data_quality: Literal["mock"] = "mock"


class KnowledgeRagAskRequest(BaseModel):
    """规程说明生成请求。先检索，再把片段交给 DeepSeek。"""

    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=10)
    station_id: str | None = Field(default=None, max_length=64)
    # 多轮会话编号；补问泵站时带上，服务端合并上一轮待补全问题。
    session_id: str | None = Field(default=None, max_length=64)


class KnowledgeRagDebugRequest(BaseModel):
    """检索诊断请求：只跑检索与门控，不调用生成模型。"""

    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=10)
    station_id: str | None = Field(default=None, max_length=64)
