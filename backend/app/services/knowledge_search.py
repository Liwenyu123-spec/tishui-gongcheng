"""本地规程检索服务。

当前阶段使用版本化的内存规则目录模拟知识检索，支持关键词匹配和确定性排序。
它不连接向量库，也不把导入正文伪装成可检索内容；后续接入 Chroma、Milvus
或数据库时，可以保留本服务的命中模型和引用格式。
"""

from dataclasses import dataclass
import re


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


def search_rules(query: str, *, metric: str | None = None, limit: int = 5) -> list[KnowledgeHit]:
    """按关键词和可选测点检索本地规程，并返回稳定排序的命中结果。"""

    normalized = query.strip().lower()
    query_terms = _terms(normalized)
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
    hits.sort(key=lambda hit: (-hit.score, hit.source_id))
    return hits[: max(1, min(limit, 10))]
