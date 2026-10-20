"""可选的大模型 Agent 路由层。

模型只负责把自然语言问题转换成受限的结构化路由结果；站点数据、告警、
供需和知识检索仍由当前项目的确定性只读工具完成。模型未启用、返回格式
错误、超时或调用失败时，调用方应回退到规则路由。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ..schemas.agent import AgentIntent
from .runtime_env import env_flag, windows_env


class AgentModelRoute(BaseModel):
    """模型允许返回的最小路由结果。"""

    intent: AgentIntent
    station_id: str | None = Field(default=None, max_length=64)
    metric: Literal["flow", "pressure", "level", "energy", "current", "unknown"] = "unknown"
    time_range: str = "当前 Mock 样本"
    control_request: bool = False


def model_status() -> dict[str, object]:
    """返回模型路由配置摘要，不泄露密钥。"""

    enabled = env_flag("AGENT_LLM_ENABLED", False)
    key_present = bool(windows_env("DEEPSEEK_API_KEY") or windows_env("DEEPSEEKAPIKEY"))
    return {
        "enabled": enabled,
        "ready": bool(enabled and key_present),
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
            "只返回 JSON，不要 Markdown，不要解释。格式："
            '{"intent":"status","station_id":null,"metric":"pressure",'
            '"time_range":"当前 Mock 样本","control_request":false}\n\n'
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
    except (ImportError, ValueError, TypeError, KeyError, ValidationError, json.JSONDecodeError, Exception):
        # 模型只是增强路由，任何外部调用或解析问题都必须安全降级。
        return None

    allowed_ids = {str(station["id"]) for station in visible_stations}
    if route.station_id is not None and route.station_id not in allowed_ids:
        route = route.model_copy(update={"station_id": None})
    if requested_station_id is not None:
        route = route.model_copy(update={"station_id": requested_station_id})
    if route.control_request:
        route = route.model_copy(update={"intent": "control_rejected"})
    return route
