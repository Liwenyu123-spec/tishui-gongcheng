"""可选的大模型 Agent 路由和答案润色层。

模型只负责把自然语言问题转换成受限的结构化路由结果，或基于后端已经执行
的只读工具摘要润色表达；站点数据、告警、供需和知识检索仍由当前项目的
确定性只读工具完成。模型未启用、返回格式错误、超时或调用失败时，调用方
应回退到规则答案。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas.agent import AgentIntent
from .runtime_env import env_flag, windows_env


class AgentModelRoute(BaseModel):
    """模型允许返回的最小路由结果。"""

    intent: AgentIntent
    station_id: str | None = Field(default=None, max_length=64)
    metric: Literal["flow", "pressure", "level", "energy", "current", "unknown"] = "unknown"
    time_range: str = "当前 Mock 样本"
    control_request: bool = False
    tools: list[str] = Field(default_factory=list, max_length=8)


class AgentModelAnswer(BaseModel):
    """模型只能返回最终自然语言，不得改写结构化事实。"""

    answer: str = Field(min_length=1, max_length=2000)


def model_status() -> dict[str, object]:
    """返回模型路由配置摘要，不泄露密钥。"""

    enabled = env_flag("AGENT_LLM_ENABLED", False)
    key_present = bool(windows_env("DEEPSEEK_API_KEY") or windows_env("DEEPSEEKAPIKEY"))
    return {
        "enabled": enabled,
        "ready": bool(enabled and key_present),
        "answer_enabled": env_flag("AGENT_LLM_ANSWER_ENABLED", False),
        "answer_ready": bool(env_flag("AGENT_LLM_ANSWER_ENABLED", False) and key_present),
        "provider": "deepseek" if key_present else None,
        "model": windows_env("AGENT_LLM_MODEL") or windows_env("DEEPSEEK_MODEL") or "deepseek-chat",
        "error": None if (not enabled or key_present) else "未配置 DEEPSEEK_API_KEY",
    }


def _extract_json(text: str) -> dict[str, object]:
    """兼容模型返回 Markdown 代码块或 JSON 前后夹带说明。"""

    cleaned = (text or "").strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回 JSON 对象")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型路由结果不是 JSON 对象")
    return value


def route_question(message: str, *, visible_stations: list[dict], requested_station_id: str | None = None) -> AgentModelRoute | None:
    """调用模型完成路由；任何异常都返回 None，由上层使用规则回退。"""

    status = model_status()
    if not status["ready"]:
        return None

    try:
        from openai import OpenAI

        station_lines = "\n".join(
            f"- {station['id']}：{station['name']}" for station in visible_stations
        ) or "- 无可见站点"
        system_prompt = (
            "你是提水工程调度平台的路由器。只做意图识别和参数抽取，不回答问题，"
            "不访问数据，不生成任何泵、阀门、PLC、DCS 或 SCADA 控制指令。\n"
            "intent 只能是 status、trend、diagnosis、supply、control_rejected、unknown。\n"
            "status=当前状态；trend=历史趋势/波动；diagnosis=异常/告警/核查/规程；"
            "supply=供需/缺口/片区；control_rejected=启停泵、开关阀、改压力、切换运行方式等现场控制；"
            "无法判断时使用 unknown。\n"
            "station_id 只能从给定站点编号中选择；没有明确站点时返回 null。\n"
            "可建议的工具只有：check_scope、read_telemetry、read_alarms、read_event_context、"
            "search_knowledge、explain_protocol、calculate_supply_balance、apply_control_boundary。\n"
            "只选择完成当前问题所需的工具，控制请求只能选择 check_scope 和 apply_control_boundary。\n"
            "只返回 JSON，不要 Markdown，不要解释。格式："
            '{"intent":"status","station_id":null,"metric":"pressure",'
            '"time_range":"当前 Mock 样本","control_request":false,'
            '"tools":["check_scope","read_telemetry"]}\n\n'
            f"当前账号可见站点：\n{station_lines}"
        )
        client = OpenAI(
            api_key=windows_env("DEEPSEEK_API_KEY") or windows_env("DEEPSEEKAPIKEY"),
            base_url=windows_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
            timeout=float(windows_env("AGENT_LLM_TIMEOUT") or "20"),
            max_retries=1,
        )
        response = client.chat.completions.create(
            model=str(status["model"]),
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )
        raw = response.choices[0].message.content or ""
        route = AgentModelRoute.model_validate(_extract_json(raw))
    except Exception:
        # 模型只是增强路由，任何外部调用或解析问题都必须安全降级。
        return None

    allowed_ids = {str(station["id"]) for station in visible_stations}
    if route.station_id is not None and route.station_id not in allowed_ids:
        route = route.model_copy(update={"station_id": None})
    if requested_station_id is not None:
        route = route.model_copy(update={"station_id": requested_station_id})
    if route.control_request:
        route = route.model_copy(update={"intent": "control_rejected"})

    from ..agent.tools import READ_ONLY_TOOLS

    selected_tools = [name for name in route.tools if name in READ_ONLY_TOOLS]
    if route.intent == "control_rejected":
        selected_tools = ["check_scope", "apply_control_boundary"]
    route = route.model_copy(update={"tools": selected_tools})
    return route


_CONTROL_WORDS = re.compile(
    r"启动泵|停止泵|启停泵|开阀|关阀|打开阀|关闭阀|调节压力|设定压力|修改设定|"
    r"下发指令|写入 PLC|写入PLC|PLC 指令|PLC指令|DCS 指令|DCS指令|SCADA 指令|SCADA指令|"
    r"start_pump|stop_pump|open_valve|close_valve",
    re.IGNORECASE,
)


def _answer_text_is_safe(text: str) -> bool:
    """拒绝可能变成现场操作指令的模型措辞，并限制输出长度。"""

    cleaned = (text or "").strip()
    return bool(cleaned) and len(cleaned) <= 2000 and not _CONTROL_WORDS.search(cleaned)


def generate_answer_from_evidence(message: str, answer: object, executions: tuple[object, ...]) -> str | None:
    """用后端工具证据润色答案；失败或越过安全边界时返回 None。

    只把用户问题、规则答案摘要和工具摘要发送给模型，不发送完整用户资料、
    内部对象或未执行工具的结果。模型返回的只有一段自然语言，结构化事实、
    引用、置信度和待确认项始终保留后端版本。
    """

    status = model_status()
    if not status["answer_ready"]:
        return None
    if getattr(answer, "intent", "unknown") == "control_rejected":
        return None

    evidence = [
        {
            "tool": str(getattr(getattr(execution, "tool", None), "name", "")),
            "summary": str(getattr(execution, "summary", ""))[:500],
            "source_ids": [str(value) for value in getattr(execution, "source_ids", ())],
            "read_only": bool(getattr(execution, "read_only", True)),
        }
        for execution in executions
    ]
    base = {
        "intent": getattr(answer, "intent", "unknown"),
        "answer": str(getattr(answer, "answer", ""))[:2000],
        "facts": [str(value)[:300] for value in getattr(answer, "facts", [])[:8]],
        "recommendations": [str(value)[:300] for value in getattr(answer, "recommendations", [])[:8]],
        "time_range": str(getattr(answer, "time_range", "")),
        "data_quality": str(getattr(answer, "data_quality", "mock")),
    }
    prompt = (
        "你是提水工程调度平台的答案整理器。只能基于后端提供的规则答案和只读工具证据，"
        "把答案改写得简洁、自然、便于调度员阅读。不得新增数字、站点、时间、告警、引用或结论；"
        "不得把 Mock 数据说成实时生产数据；不得生成或建议任何泵、阀门、PLC、DCS、SCADA 控制操作。"
        "只返回 JSON，格式为 {\"answer\":\"...\"}，不要 Markdown，不要解释。\n\n"
        f"用户问题：{message}\n"
        f"规则答案与结构化事实：{json.dumps(base, ensure_ascii=False)}\n"
        f"只读工具证据：{json.dumps(evidence, ensure_ascii=False)}"
    )
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=windows_env("DEEPSEEK_API_KEY") or windows_env("DEEPSEEKAPIKEY"),
            base_url=windows_env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
            timeout=float(windows_env("AGENT_LLM_TIMEOUT") or "20"),
            max_retries=1,
        )
        response = client.chat.completions.create(
            model=str(status["model"]),
            temperature=0,
            messages=[
                {"role": "system", "content": "只返回符合要求的 JSON。"},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        generated = AgentModelAnswer.model_validate(_extract_json(raw)).answer.strip()
    except Exception:
        return None
    return generated if _answer_text_is_safe(generated) else None
