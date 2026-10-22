"""本地规程检索服务。

内置规程和内存文档使用关键词打分。已批准且仍在有效期内的导入正文优先从 Chroma
召回，分数与关键词分同一量级。Chroma 不可用时回退到内存正文检索。
"""

from datetime import datetime, timezone
from dataclasses import dataclass
import json
import re

from ..data.knowledge import _KNOWLEDGE, _KNOWLEDGE_CONTENT
from .rag_chroma import get_rag_store


@dataclass(frozen=True)
class KnowledgeRule:
    """一条可以被 Agent 引用的本地规程条目。"""

    source_id: str
    title: str
    version: str
    metric: str
    keywords: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class KnowledgeHit:
    """一次检索命中的规程及其确定性相关度。"""

    source_id: str
    title: str
    version: str
    detail: str
    score: int
    source: str = "mock-rule"
    filename: str = ""
    station_ids: tuple[str, ...] = ()
    chunk_index: int | None = None
    location: str = "内置规程"
    category: str = "规程"
    confidence: str = "normal"
    # 重排概率（0~1）。未启用重排时为 None，门控据此决定是否使用该信号。
    rerank: float | None = None
    # 邻域上下文（当前分片 + 前后条款）。结构化切片后单条可能很短，
    # 生成与忠实度校验用这份更完整的文本，detail 仍保留精确分片用于引用展示。
    context: str = ""


# 规则目录与 Agent 诊断分支共用稳定编号，便于回答、审计和回放相互追踪。
KNOWLEDGE_RULES: tuple[KnowledgeRule, ...] = (
    KnowledgeRule(
        source_id="mock-knowledge-flow-v1.2",
        title="泵站流量异常核查规程",
        version="v1.2",
        metric="flow",
        keywords=("流量", "泵站", "异常", "下降", "核查"),
        detail="先核对入口压力、泵组运行电流和下游压力，再决定是否升级人工处置。",
    ),
    KnowledgeRule(
        source_id="mock-knowledge-pressure-v1.1",
        title="输水压力异常处置规程",
        version="v1.1",
        metric="pressure",
        keywords=("压力", "输水", "波动", "异常", "阀门"),
        detail="先确认上下游压力测点有效，再核查阀门状态和泵组运行记录。",
    ),
    KnowledgeRule(
        source_id="mock-knowledge-level-v1.0",
        title="泵站水位巡检规程",
        version="v1.0",
        metric="level",
        keywords=("水位", "液位", "泵站", "趋势", "来水"),
        detail="连续观察水位趋势并核对来水情况，禁止仅凭单个 Mock 测点下结论。",
    ),
    KnowledgeRule(
        source_id="mock-knowledge-current-v1.0",
        title="泵组电流异常核查规程",
        version="v1.0",
        metric="current",
        keywords=("电流", "电机", "负荷", "保护", "运行记录"),
        detail="核查电机负荷、运行记录和保护状态，必要时交由现场负责人确认。",
    ),
    KnowledgeRule(
        source_id="mock-knowledge-confined-space-v1.0",
        title="有限空间与临水作业安全规程",
        version="v1.0",
        metric="safety",
        keywords=("有限空间", "阀门井", "下井", "通风", "两人以上", "外部监护", "安全"),
        detail="进入集水井、阀门井等有限空间前必须通风并检测气体；有限空间作业必须两人以上，一人在外监护，全程保持联络。",
    ),
)


def _terms(value: str) -> tuple[str, ...]:
    """提取中文二字/三字片段、英文标识和数字。

    连续中文整句不能当成一个词，否则「二泵站流量下降后按规程先核查什么」
    对不上内置规程里的「流量」「下降」。
    """

    tokens: list[str] = []
    for block in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z][a-zA-Z0-9_-]*|\d+", (value or "").lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", block):
            tokens.extend(block[i : i + 2] for i in range(max(1, len(block) - 1)))
            if len(block) >= 3:
                tokens.extend(block[i : i + 3] for i in range(len(block) - 2))
        else:
            tokens.append(block)
    return tuple(dict.fromkeys(tokens))


def _is_current(document, now: datetime) -> bool:
    """判断文档是否处于现行且有效时间窗口。"""

    if document.status != "valid":
        return False
    effective_from = document.effective_from
    effective_to = document.effective_to
    if effective_from is not None:
        effective_from = effective_from if effective_from.tzinfo else effective_from.replace(tzinfo=timezone.utc)
        if now < effective_from:
            return False
    if effective_to is not None:
        effective_to = effective_to if effective_to.tzinfo else effective_to.replace(tzinfo=timezone.utc)
        if now >= effective_to:
            return False
    return True


def _document_applies(document, *, station_id: str | None, visible_station_ids: set[str] | None) -> bool:
    """按请求站点和账号可见范围过滤知识文档。"""

    applicable = set(document.station_ids)
    if station_id is not None and applicable and station_id not in applicable:
        return False
    if visible_station_ids is not None and applicable and not applicable.intersection(visible_station_ids):
        return False
    return True


def search_rules(
    query: str,
    *,
    original_query: str | None = None,
    metric: str | None = None,
    limit: int = 5,
    station_id: str | None = None,
    visible_station_ids: set[str] | None = None,
    now: datetime | None = None,
) -> list[KnowledgeHit]:
    """按关键词、状态、有效期和站点检索内置规则及已批准导入文档。"""

    normalized = query.strip().lower()
    # 同时保留原始问句和归一化问句的词项，避免术语替换误伤站点编号或告警编码。
    query_terms = tuple(dict.fromkeys((*_terms(normalized), *_terms((original_query or "").lower()))))
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    hits: list[KnowledgeHit] = []
    for rule in KNOWLEDGE_RULES:
        score = 0
        if metric and rule.metric == metric:
            score += 8
        searchable = (rule.title + rule.detail + " ".join(rule.keywords)).lower()
        for term in query_terms:
            if term in searchable:
                score += 2
        if normalized and normalized in searchable:
            score += 3
        if score:
            hits.append(
                KnowledgeHit(
                    source_id=rule.source_id,
                    title=f"{rule.title} {rule.version}",
                    version=rule.version,
                    detail=rule.detail,
                    score=score,
                    location="内置规程",
                    category="规程",
                )
            )
    metric_terms = {
        "flow": ("flow", "流量"),
        "pressure": ("pressure", "压力"),
        "level": ("level", "水位", "液位"),
        "current": ("current", "电流"),
    }.get(metric or "", ())
    # 第一阶段 RAG：优先从独立 Chroma 集合召回已导入资料。业务元数据仍由当前
    # 文档模型和权限过滤负责，后续可以把这部分替换成 MySQL 查询。
    indexed_ids: set[str] = set()
    store = get_rag_store()
    if store is not None:
        for item in store.search(
            normalized,
            limit=max(1, min(limit, 10)),
            station_id=station_id,
            visible_station_ids=visible_station_ids,
        ):
            metadata = item["metadata"]
            document_id = str(item["document_id"])
            indexed_ids.add(document_id)
            try:
                station_ids = tuple(json.loads(str(metadata.get("station_ids") or "[]")))
            except (TypeError, ValueError, json.JSONDecodeError):
                station_ids = ()
            chunk_index = metadata.get("chunk_index")
            chunk_number = int(chunk_index) if chunk_index is not None and str(chunk_index) != "" else None
            # 优先用「上下文范围」做引用定位：模型看到的是当前条款加相邻条款，
            # 只写一条会与实际依据不符。旧索引没有这些字段时退回分片序号。
            section_path = str(metadata.get("section_path") or "").strip()
            context_label = str(item.get("context_label") or "").strip()
            # Chroma 负责语义召回，关键词重合度补足泵站编号、告警编码和专业术语的精确匹配。
            chunk_searchable = f"{metadata.get('title', '')} {metadata.get('filename', '')} {item.get('text', '')}".lower()
            keyword_bonus = sum(1 for term in query_terms if term and term in chunk_searchable)
            hits.append(
                KnowledgeHit(
                    source_id=document_id,
                    title=f"{metadata.get('title') or metadata.get('filename') or document_id} {metadata.get('version', '')}".strip(),
                    version=str(metadata.get("version") or "1.0"),
                    detail=str(item["text"]).replace("\r", " ").replace("\n", " ")[:500],
                    score=int(item["score"]) + keyword_bonus,
                    source="chroma-document",
                    filename=str(metadata.get("filename") or ""),
                    station_ids=station_ids,
                    chunk_index=chunk_number,
                    location=context_label or section_path
                    or (f"分片 {chunk_number + 1}" if chunk_number is not None else "正文"),
                    category=str(metadata.get("category") or "规程"),
                    confidence=str(item.get("confidence") or "normal"),
                    rerank=(float(item["rerank"]) if item.get("rerank") is not None else None),
                    context=str(item.get("context") or ""),
                )
            )

    # Chroma 不可用时保留原有内存检索作为回退；已进入 Chroma 的文档避免重复展示。
    for document_id, document in _KNOWLEDGE.items():
        if document_id in indexed_ids:
            continue
        if not _is_current(document, current_time) or not _document_applies(
            document,
            station_id=station_id,
            visible_station_ids=visible_station_ids,
        ):
            continue
        content = _KNOWLEDGE_CONTENT.get(document_id, "")
        searchable = f"{document.title} {document.filename} {content}".lower()
        score = 0
        for term in query_terms:
            if term in searchable:
                score += 2
            if term in document.title.lower():
                score += 2
        if normalized and normalized in searchable:
            score += 3
        if metric_terms and any(term in searchable for term in metric_terms):
            score += 4
        if station_id is not None and station_id in document.station_ids:
            score += 10
        if score:
            detail = content.strip().replace("\r", " ").replace("\n", " ")[:500]
            hits.append(
                KnowledgeHit(
                    source_id=document_id,
                    title=f"{document.title} {document.version}",
                    version=document.version,
                    detail=detail or "已批准文档，正文未提供可展示摘要",
                    score=score,
                    source="mock-document",
                    filename=document.filename,
                    station_ids=tuple(document.station_ids),
                    location="正文摘要",
                    category=document.category,
                )
            )
    hits.sort(key=lambda hit: (-hit.score, hit.source_id))
    return hits[: max(1, min(limit, 10))]
