"""知识库文档的内存 Mock 数据。"""

from ..schemas.knowledge import KnowledgeDocument


# 服务重启后会清空导入文档，当前仅保存元数据和正文长度。
# 文档正文不会写入当前 Mock 存储，content_length 仅用于列表展示。
_KNOWLEDGE: dict[str, KnowledgeDocument] = {}
