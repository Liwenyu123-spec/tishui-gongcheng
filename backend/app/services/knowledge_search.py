"""本地规程检索服务。

当前阶段使用版本化的内存规则目录模拟知识检索，支持关键词匹配和确定性排序。
它不连接向量库，也不把导入正文伪装成可检索内容；后续接入 Chroma、Milvus
或数据库时，可以保留本服务的命中模型和引用格式。
"""

from datetime import datetime, timezone
from dataclasses import dataclass
import re

from ..data.knowledge import _KNOWLEDGE, _KNOWLEDGE_CONTENT


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
)


def _terms(value: str) -> tuple[str, ...]:
    """提取中文词组、英文标识和数字，避免依赖外部分词库。"""

    return tuple(dict.fromkeys(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_-]*|\d+", value.lower())))


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
    metric: str | None = None,
    limit: int = 5,
    station_id: str | None = None,
    visible_station_ids: set[str] | None = None,
    now: datetime | None = None,
) -> list[KnowledgeHit]:
    """按关键词、状态、有效期和站点检索内置规则及已批准导入文档。"""

    normalized = query.strip().lower()
    query_terms = _terms(normalized)
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
                )
            )
    metric_terms = {
        "flow": ("flow", "流量"),
        "pressure": ("pressure", "压力"),
        "level": ("level", "水位", "液位"),
        "current": ("current", "电流"),
    }.get(metric or "", ())
    for document_id, document in _KNOWLEDGE.items():
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
            score += 6
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
                )
            )
    hits.sort(key=lambda hit: (-hit.score, hit.source_id))
    return hits[: max(1, min(limit, 10))]
