"""知识库文档的内存视图。

真正的数据落在 `backend/data/knowledge`（见 `knowledge_store`）。本模块只保留
两个字典供路由和检索层读取，并在启动或重建索引时调用 `reload_from_store()`
从磁盘刷新。这样其它模块继续 `from .knowledge import _KNOWLEDGE` 就能拿到
最新数据，不必改动 import 关系。

注意：这里必须原地 `clear()` + `update()`，不能重新绑定变量名，否则其它模块
持有的仍是旧字典引用。
"""

from ..schemas.knowledge import KnowledgeDocument
from .knowledge_store import load_all

# 文档元数据和正文的内存视图；启动时从落盘文件载入，不再随服务重启丢失。
_KNOWLEDGE: dict[str, KnowledgeDocument] = {}
_KNOWLEDGE_CONTENT: dict[str, str] = {}


def reload_from_store() -> dict[str, int]:
    """从落盘文件重新加载内存视图，返回文档数量和正文数量。"""

    documents, contents = load_all()
    # 原地更新字典，保证已经 import 过 _KNOWLEDGE 的模块看到同一份数据。
    _KNOWLEDGE.clear()
    _KNOWLEDGE.update(documents)
    _KNOWLEDGE_CONTENT.clear()
    _KNOWLEDGE_CONTENT.update(contents)
    return {"documents": len(_KNOWLEDGE), "contents": len(_KNOWLEDGE_CONTENT)}


# 导入本模块即完成一次加载，让服务启动后知识库立即可见。
reload_from_store()
