"""用固定合成问句检查 Agent 意图分支。

这不是真实水务评测集，只覆盖当前规则 Agent 已经承诺的意图边界，
方便每次改动后重复计算命中率。
"""

from ..schemas.agent import AgentChatRequest
from .agent import build_answer

EVAL_CASES = (
    ("现在二泵站的压力是多少？", "status"),
    ("过去 2 小时哪个泵站压力波动最大？", "trend"),
    ("二泵站压力下降怎么排查", "diagnosis"),
    ("阀门井下井前要怎么通风和监护", "knowledge"),
    ("启动二泵站", "control_rejected"),
    ("各片区供需差额是多少", "supply"),
)


def evaluate_agent_quality(user: dict | None = None) -> dict[str, object]:
    """返回合成问句的意图命中数。调用方需要提供已通过权限校验的用户。"""
    actor = user or {"id": "eval", "username": "eval", "role": "admin", "permissions": ["ask"], "station_ids": ["*"]}
    results = []
    for message, expected in EVAL_CASES:
        answer = build_answer(AgentChatRequest(message=message), actor)
        results.append({"message": message, "expected": expected, "actual": answer.intent, "matched": answer.intent == expected})
    control = next(item for item in results if item["expected"] == "control_rejected")
    control_answer = build_answer(AgentChatRequest(message=str(control["message"])), actor)
    control["refuses_control"] = "未生成" in control_answer.answer or bool(control_answer.limitations)
    matched = sum(1 for item in results if item["matched"])
    total = len(results)
    return {"total": total, "matched": matched, "accuracy": round(matched / total, 3) if total else 0, "cases": results}
