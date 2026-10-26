from datetime import datetime, timedelta, timezone

from app.agent.orchestrator import coordinate
from app.schemas.agent import AgentAnswer
from app.services.agent_eval import evaluate_agent_quality
from app.services.agent_registry import register_agent
from app.services.agent_runs import cleanup_expired_tasks, save_task_snapshot, task_snapshot
from app.services.document_extract import format_pdf_pages
from app.services.knowledge_search import KnowledgeHit, detect_conflicts


def test_flow_drop_selects_check_skill():
    from app.agent.orchestrator import coordinate
    from app.schemas.agent import AgentAnswer
    from datetime import datetime, timezone

    answer = AgentAnswer(
        request_id="req-skill",
        intent="diagnosis",
        answer="测试",
        facts=[],
        recommendations=[],
        citations=[],
        source="mock-rule",
        generated_at=datetime.now(timezone.utc),
    )
    plan = coordinate(answer, "二泵站流量下降怎么排查")
    assert plan.skill_id == "flow-drop-check"
    from app.services.agent_skills import list_skills, select_skill
    catalog = list_skills()
    assert {item["id"] for item in catalog} >= {"station-status", "alarm-diagnosis", "knowledge-lookup", "supply-balance"}
    assert all("start_pump" not in item["allowed_tools"] for item in catalog)
    status = select_skill("二泵站现在流量是多少", "status")
    assert status and status["id"] == "station-status"
    assert status["requires_confirmation"] is False


def test_rejected_run_cannot_resume_snapshot():
    from app.services.agent_runs import decide_run, save_task_snapshot, task_snapshot

    save_task_snapshot("run-reject", {"message": "启动二泵站", "user_id": "admin"})
    result = decide_run("run-reject", "reject", "不允许现场控制")
    assert result["status"] == "rejected"
    assert task_snapshot("run-reject") is None


def test_custom_agent_joins_matching_branch():
    register_agent("pressure_reader", "只读压力复核", ["read_telemetry"])
    answer = AgentAnswer(
        request_id="req-custom",
        intent="status",
        answer="测试",
        facts=[],
        recommendations=[],
        citations=[],
        source="mock-rule",
        generated_at=datetime.now(timezone.utc),
    )
    plan = coordinate(answer, "现在二泵站的压力是多少？")
    assert "pressure_reader" in plan.collaborating_agents


def test_expired_approval_snapshot_is_removed():
    save_task_snapshot("run-old", {"message": "旧任务", "user_id": "admin"})
    from app.services import agent_runs
    agent_runs._tasks["run-old"]["saved_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    removed = cleanup_expired_tasks()
    assert "run-old" in removed
    assert task_snapshot("run-old") is None


def test_pdf_continues_table_when_next_page_has_no_header():
    text = format_pdf_pages([
        (1, "设备    阈值\n二泵站    105"),
        (2, "四泵站    0.6"),
    ])
    assert "跨页表格" in text
    assert "四泵站" in text
    assert text.count("[表格") + text.count("[跨页表格") == 1


def test_csv_and_scope_helpers():
    from app.services.document_extract import extract_text
    from app.services.knowledge_generate import infer_knowledge_scope

    text, parser = extract_text("limits.csv", "设备,阈值\n二泵站,105\n".encode("utf-8"))
    assert parser == "csv"
    assert "二泵站\t105" in text
    assert infer_knowledge_scope("抢修预案怎么执行") == "应急预案"
    assert infer_knowledge_scope("现在压力是多少") is None


def test_pdf_cross_page_table_and_block_location():
    text = format_pdf_pages([
        (1, "设备    阈值    单位\n二泵站    105    百分比"),
        (2, "设备    阈值    单位\n四泵站    0.6    兆帕\n\n正文说明继续有效。"),
    ])
    assert "跨页表格" in text
    assert "四泵站" in text
    assert "[第 2 页 · 区块 1]" in text
    assert "正文说明继续有效。" in text


def test_conflict_prefers_later_effective_document():
    older = KnowledgeHit(source_id="doc-old", title="二泵站规程", version="3.0", detail="二泵站启泵前可以不核对电流", score=9, effective_from="2024-01-01T00:00:00+00:00")
    newer = KnowledgeHit(source_id="doc-new", title="二泵站规程", version="1.2", detail="二泵站启泵前不得跳过电流核对", score=7, effective_from="2026-06-01T00:00:00+00:00", station_ids=("pump-02",))
    conflicts = detect_conflicts([older, newer])
    assert conflicts[0]["preferred_source_id"] == "doc-new"
    assert "指定站点" in conflicts[0]["preferred_reason"]


def test_conflict_prefers_higher_version():
    older = KnowledgeHit(source_id="doc-old", title="二泵站规程", version="1.0", detail="二泵站启泵前可以不核对电流", score=8)
    newer = KnowledgeHit(source_id="doc-new", title="二泵站规程", version="2.1", detail="二泵站启泵前不得跳过电流核对", score=7)
    conflicts = detect_conflicts([older, newer])
    assert conflicts
    assert conflicts[0]["preferred_source_id"] == "doc-new"


def test_synthetic_agent_quality_cases_match_intents():
    report = evaluate_agent_quality()
    assert report["matched"] == report["total"]
    assert report["accuracy"] == 1.0
