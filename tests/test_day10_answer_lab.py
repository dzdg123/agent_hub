"""验证实验脚本的真实模式确实经过 HTTP 客户端，不使用预设回复。"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
import respx

from research_agent.config import Settings


@pytest.fixture
def lab(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "examples" / "day10_answer_lab.py"
    spec = importlib.util.spec_from_file_location("day10_answer_lab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "Settings", lambda **kwargs: Settings(
        _env_file=None, deepseek_api_key="offline-test-key",
        deepseek_model="deepseek-chat", deepseek_base_url="https://api.deepseek.com",
    ))
    return module


@pytest.mark.asyncio
@respx.mock
async def test_env_path_is_anchored_to_project_not_working_directory(lab, monkeypatch, tmp_path):
    loaded_paths = []

    def load_settings(**kwargs):
        loaded_paths.append(kwargs["_env_file"])
        return Settings(
            _env_file=None, deepseek_api_key="offline-test-key",
            deepseek_model="deepseek-flash", deepseek_base_url="https://api.deepseek.com",
        )

    monkeypatch.setattr(lab, "Settings", load_settings)
    monkeypatch.chdir(tmp_path)
    mock_models()
    await lab.create_live_client(None, 0)
    assert loaded_paths == [Path(lab.__file__).resolve().parents[1] / ".env"]


def mock_models():
    return respx.get("https://api.deepseek.com/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]}),
    )


def model_response(source_id="doc-experiment"):
    return httpx.Response(200, json={
        "id": "actual-http-response-id",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "status": "answered",
            "claims": [{
                "text": "实验有三个步骤。", "kind": "fact",
                "evidence": [{"source_id": source_id, "quote": "实验有三个步骤。"}],
            }],
            "limitations": [],
        }, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


def test_default_is_one_real_case(lab):
    args = lab.parse_args([])
    assert args.mode == "live"
    assert args.case == "success"
    assert args.retries == 0


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("case", ["success", "injection"])
async def test_live_mode_uses_http_reply_and_actual_usage(lab, capsys, case):
    models = mock_models()
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=model_response(),
    )
    code = await lab.main(lab.parse_args(["--case", case, "--show-messages"]))
    assert code == 0
    assert models.call_count == route.call_count == 1
    record = json.loads(capsys.readouterr().out)[0]
    assert record["mode"] == "live"
    assert record["usage_is_simulated"] is False
    assert record["model"] == "deepseek-flash"
    assert record["model_selection"] == "temporary_available_model"
    assert "expectation_met" not in record
    assert record["result"]["usage"]["total_tokens"] == 120
    assert "草稿预览" in record["markdown_preview"]
    assert "语义审核状态：待审核" in record["markdown_preview"]
    assert record["result"]["attempts"][0]["reply"]["request_id"] == "actual-http-response-id"
    payload = json.loads(route.calls[0].request.content)
    assert payload["model"] == "deepseek-flash"
    assert payload["max_tokens"] == 2048
    question_payload = json.loads(payload["messages"][1]["content"])
    assert ("web-fake" in question_payload["context"]) == (case == "injection")


@pytest.mark.asyncio
@respx.mock
async def test_live_rejects_fake_id_without_faking_expected_failure(lab, capsys):
    mock_models()
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=model_response("web-fake"),
    )
    assert await lab.main(lab.parse_args(["--case", "injection"])) == 1
    record = json.loads(capsys.readouterr().out)[0]
    assert route.call_count == record["generation_requests"] == 2
    assert record["result"]["status"] == "validation_failed"
    assert record["result"]["draft"] is None
    assert record["result"]["usage"]["total_tokens"] == 240


@pytest.mark.asyncio
@respx.mock
async def test_custom_question_and_evidence_reach_actual_request(lab, capsys):
    mock_models()
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({
                "status": "insufficient_evidence", "claims": [],
                "limitations": ["当前资料未提供年龄信息。"],
            }, ensure_ascii=False)},
        }]}),
    )
    assert await lab.main(lab.parse_args([
        "--question", "你几岁了？", "--evidence", "这份资料只介绍实验。",
    ])) == 0
    payload = json.loads(json.loads(route.calls[0].request.content)["messages"][1]["content"])
    assert payload["question"] == "你几岁了？"
    assert "这份资料只介绍实验。" in payload["context"]
    assert json.loads(capsys.readouterr().out)[0]["result"]["draft"]["status"] == "insufficient_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["no_candidates", "no_allowed_sources", "budget_exhausted"])
async def test_empty_cases_do_not_need_credentials_or_http(lab, monkeypatch, capsys, case):
    def forbidden():
        pytest.fail("空证据场景不应加载 API 凭据或创建客户端")
    monkeypatch.setattr(lab, "Settings", forbidden)
    assert await lab.main(lab.parse_args(["--case", case])) == 0
    record = json.loads(capsys.readouterr().out)[0]
    assert record["result"]["status"] == case
    assert record["generation_requests"] == 0
    assert record["deepseek_raw_replies"] == []


@pytest.mark.asyncio
@respx.mock
async def test_explicit_unavailable_model_does_not_fallback_to_mock(lab):
    mock_models()
    with pytest.raises(ValueError, match="不可用"):
        await lab.main(lab.parse_args(["--model", "missing-model"]))


@pytest.mark.asyncio
async def test_old_mock_cases_still_explicitly_available(lab, capsys):
    assert await lab.main(lab.parse_args(["--mode", "mock", "--case", "all"])) == 0
    records = json.loads(capsys.readouterr().out)
    assert len(records) == 7
    assert all(record["mode"] == "mock" and record["usage_is_simulated"] for record in records)


@pytest.mark.parametrize("case", ["repair", "invalid", "network_error"])
def test_live_does_not_pretend_to_force_mock_outcomes(lab, case):
    with pytest.raises(SystemExit):
        lab.parse_args(["--case", case])


@pytest.mark.asyncio
async def test_markdown_format_prints_preview_and_usage_separately(lab, capsys):
    assert await lab.main(lab.parse_args([
        "--mode", "mock", "--case", "success", "--format", "markdown",
    ])) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("# ")
    assert "草稿预览" in captured.out
    assert '[doc\\-experiment](#ref-1)' in captured.out
    assert '<a id="ref-1"></a>' in captured.out
    assert json.loads(captured.err)["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_failed_draft_is_not_markdown_report(lab, capsys):
    assert await lab.main(lab.parse_args([
        "--mode", "mock", "--case", "invalid", "--format", "markdown",
    ])) == 0  # Mock 的故意失败符合预期，不代表报告审核通过。
    text = capsys.readouterr().out
    assert "当前没有可渲染草稿" in text
    assert "web-fake" not in text
    assert "## 参考资料" not in text
