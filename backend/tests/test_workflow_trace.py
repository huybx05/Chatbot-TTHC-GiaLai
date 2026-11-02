from __future__ import annotations

import json

from backend.app.workflow import trace_log
from backend.app.workflow.run import RunResult


def test_run_result_to_dict_co_trace_snapshot() -> None:
    result = RunResult(
        question="câu rewrite",
        state={
            "original_question": "câu gốc",
            "retrieval_question": "câu rewrite",
            "rewrite": {"used": True, "anchor": {"code": "1.001699", "name": "A"}},
            "memory": {"topics": [{"order": 1, "procedure_code": "1.001699"}]},
        },
        ms=1,
    )

    payload = result.to_dict()

    assert payload["trace"]["original_question"] == "câu gốc"
    assert payload["trace"]["retrieval_question"] == "câu rewrite"
    assert payload["trace"]["rewrite"]["used"] is True
    assert payload["trace"]["memory"]["topics"][0]["procedure_code"] == "1.001699"


def test_run_result_to_dict_tach_ba_tang_procedure() -> None:
    result = RunResult(
        question="câu hỏi",
        state={
            "candidate_procedures": [
                {"code": "A", "name": "Candidate", "score": 0.9, "source": "vector"}
            ],
            "grounded_procedure": {
                "code": "A",
                "name": "Grounded",
                "source": "grounding",
            },
            "answered_procedure": {
                "code": "A",
                "name": "Answered",
                "source": "grounded",
            },
        },
        ms=1,
    )

    payload = result.to_dict()

    assert payload["candidate_procedures"][0]["code"] == "A"
    assert payload["grounded_procedure"]["source"] == "grounding"
    assert payload["answered_procedure"]["source"] == "grounded"


class _Result:
    question = "Thủ tục 1.001699 cần hồ sơ gì?"
    outcome = "answered"
    branch = "executor"
    signal = "ok"
    reason = "plan: 1/1 ý có dữ liệu"
    ms = 12
    ran = True
    state = {
        "original_question": "Còn hồ sơ thì sao?",
        "retrieval_question": "Hồ sơ thủ tục 1.001699 gồm gì?",
        "rewrite": {
            "used": True,
            "is_followup": True,
            "confidence": 0.92,
            "reason": "",
            "anchor": {"code": "1.001699", "name": "Thủ tục A"},
        },
        "memory": {
            "summary": "Đã hỏi thủ tục A.",
            "recent_turns": [{"role": "user"}, {"role": "assistant"}],
            "topics": [
                {
                    "order": 1,
                    "procedure_code": "1.001699",
                    "procedure_name": "Thủ tục A",
                }
            ],
            "active_procedure": {"code": "1.001699", "name": "Thủ tục A"},
            "recalled_turns": [],
        },
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
    assert rows[0]["question"] == _Result.state["original_question"]
    assert rows[0]["groundings"][0]["code"] == "1.001699"
    assert rows[0]["evidence"][0]["content"] == "Hồ sơ cần nộp"


def test_trace_v3_co_du_truong_chan_doan(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()
    result.state = {
        **result.state,
        "plan_class": "direct",
        "plan_class_reason": "chủ thể đã xác định",
        "request_plan_class": [{"request_index": 0, "plan_class": "direct"}],
        "verification": {"status": "ok", "issues": []},
        "thieu": [],
    }
    trace_log.append(result, source="chat_stream", phase="final")
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["trace_version"] == 3
    assert row["source"] == "chat_stream"
    assert row["phase"] == "final"
    assert row["plan_class"] == "direct"
    assert row["verification"]["status"] == "ok"
    assert row["question"] == "Còn hồ sơ thì sao?"
    assert row["retrieval_question"] == "Hồ sơ thủ tục 1.001699 gồm gì?"
    assert row["rewrite"]["used"] is True
    assert row["rewrite"]["anchor"]["code"] == "1.001699"
    assert row["memory"]["active_procedure"]["code"] == "1.001699"
    assert row["memory"]["recent_turns"] == 2
    assert "discovery" not in row
    assert "request_plan_class" not in row
    assert "fallbacks" not in row


def test_trace_ghi_ba_tang_procedure(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()
    result.state = {
        **result.state,
        "candidate_procedures": [
            {"code": "1.001699", "name": "Candidate", "score": 0.9, "source": "vector"}
        ],
        "grounded_procedure": {
            "code": "1.001699",
            "name": "Grounded",
            "source": "grounding",
        },
        "answered_procedure": {
            "code": "1.001699",
            "name": "Answered",
            "source": "grounded",
            "evidence_count": 1,
        },
    }

    trace_log.append(result, source="chat")

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["candidate_procedures"][0]["code"] == "1.001699"
    assert row["grounded_procedure"]["source"] == "grounding"
    assert row["answered_procedure"]["source"] == "grounded"


def test_trace_chat_va_stream_cung_schema(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()

    trace_log.append(result, source="chat")
    state = dict(result.state)
    state["ms"] = result.ms
    state["total_ms"] = result.ms
    trace_log.append_from_state(
        result.question,
        state,
        ms=result.ms,
        source="chat_stream",
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    ignore = {"trace_id", "timestamp", "source"}
    assert set(rows[0]) - ignore == set(rows[1]) - ignore
    for key in set(rows[0]) - ignore:
        assert rows[0][key] == rows[1][key], key


def test_trace_khong_dump_toan_bo_memory_va_frame(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()
    result.state = {
        **result.state,
        "memory": {
            "summary": "NỘI DUNG TÓM TẮT KHÔNG NÊN CÓ TRONG LOG",
            "recent_turns": [{"content": "nội dung dài"}] * 6,
            "topics": [
                {
                    "order": index,
                    "procedure_code": f"1.00{index:04d}",
                    "procedure_name": f"Thủ tục {index}",
                }
                for index in range(12)
            ],
            "active_procedure": {"code": "1.001699", "name": "Thủ tục A"},
        },
        "question_frame": {
            "scope": "tthc",
            "subject_mentions": [{"type": "procedure", "text": "x" * 500}],
            "requests": [{"text": "y" * 500, "facet": "fee"}],
        },
        "evidence": [
            {"kind": "section", "content": f"nội dung {index}"}
            for index in range(8)
        ],
    }

    trace_log.append(result)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    assert "summary" not in row["memory"]
    assert row["memory"]["summary_chars"] > 0
    assert len(row["memory"]["topics"]) == 10
    assert len(row["evidence"]) == 6
    assert len(row["question_frame"]["subject_mentions"][0]["text"]) <= 300
    assert len(row["question_frame"]["requests"][0]["text"]) <= 300


def test_trace_nhan_snapshot_tu_stream_dict(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))

    trace_log.append_from_state(
        "câu gốc",
        {
            "outcome": "answered",
            "trace": {
                "original_question": "câu gốc",
                "retrieval_question": "câu rewrite (mã 1.001699)",
                "rewrite": {
                    "used": True,
                    "is_followup": True,
                    "confidence": 0.9,
                    "reason": "low_confidence",
                    "attempts": 2,
                    "latency_ms": 31,
                    "error_type": "validation",
                    "anchor": {"code": "1.001699", "name": "Thủ tục A"},
                },
                "memory": {
                    "topics": [
                        {
                            "order": 1,
                            "procedure_code": "1.001699",
                            "procedure_name": "Thủ tục A",
                        }
                    ]
                },
            },
        },
        source="chat_stream",
        phase="final",
    )
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    assert row["retrieval_question"] == "câu rewrite (mã 1.001699)"
    assert row["rewrite"]["used"] is True
    assert row["rewrite"]["reason"] == "low_confidence"
    assert row["rewrite"]["attempts"] == 2
    assert row["rewrite"]["latency_ms"] == 31
    assert row["rewrite"]["error_type"] == "validation"
    assert row["memory"]["topics"][0]["code"] == "1.001699"


def test_trace_rewrite_false_khi_khong_co_rewrite(monkeypatch, tmp_path) -> None:
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("WORKFLOW_TRACE_JSONL_PATH", str(path))
    result = _Result()
    result.state = {**result.state, "rewrite": {}}

    trace_log.append(result)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    assert row["rewrite"] == {"used": False}
