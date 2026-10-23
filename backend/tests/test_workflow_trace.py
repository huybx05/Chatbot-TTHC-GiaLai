from __future__ import annotations

import json

from backend.app.workflow import trace_log


class _Result:
    question = "Thủ tục 1.001699 cần hồ sơ gì?"
    outcome = "answered"
    branch = "executor"
    signal = "ok"
    reason = "plan: 1/1 ý có dữ liệu"
    ms = 12
    ran = True
    state = {
        "question_frame": {"scope": "tthc"},
        "groundings": [{"code": "1.001699", "status": "resolved"}],
        "plan": {"tasks": []},
        "coverage": [{"status": "covered"}],
        "evidence": [{"kind": "section", "content": "Hồ sơ cần nộp", "request_index": 0}],
    }


def test_append_writes_one_json_object(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))

    trace_log.append(_Result())

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["question"] == _Result.question
    assert rows[0]["groundings"][0]["code"] == "1.001699"
    assert rows[0]["evidence"][0]["content"] == "Hồ sơ cần nộp"


def test_trace_v2_co_du_truong_chan_doan(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()
    result.state = {
        **result.state,
        "plan_class": "direct",
        "plan_class_reason": "chủ thể đã xác định",
        "request_plan_class": [{"request_index": 0, "plan_class": "direct"}],
        "discovery": [{"code": "1.001699", "result_kind": "discovery"}],
        "verification": {"status": "ok", "issues": []},
        "thieu": [],
    }
    trace_log.append(result, source="chat_stream", phase="final")
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["trace_version"] == 2
    assert row["source"] == "chat_stream"
    assert row["phase"] == "final"
    assert row["plan_class"] == "direct"
    assert row["discovery"][0]["code"] == "1.001699"
    assert row["verification"]["status"] == "ok"
