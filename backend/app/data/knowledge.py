"""知识库文档的内存 Mock 数据。"""

from ..schemas.knowledge import KnowledgeDocument


# 服务重启后会清空导入文档；正文暂存在进程内，供 Mock 检索服务建立临时索引。
# 后续接入数据库或向量库时，只替换本存储层，不改变文档状态和引用模型。
_KNOWLEDGE: dict[str, KnowledgeDocument] = {}
_KNOWLEDGE_CONTENT: dict[str, str] = {}
