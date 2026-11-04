import json
from pathlib import Path

import httpx
import pytest

from media_rag_bench.cli import main
from media_rag_bench.generation.openai import movie_instructions

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mock_openai(monkeypatch):
    client_class = httpx.Client
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("OPENAI_MODEL", "fixture-model")

    def install(handler):
        monkeypatch.setattr(
            "media_rag_bench.cli.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


def completed_response(count=2):
    response = {
        "domain": "movies",
        "recommendations": [
            {
                "title": f"Fictional Film {index + 1}",
                "release_year": 2005,
                "explanation": "An original fixture explanation about the requested theme.",
                "catalog_id": None,
                "evidence_ids": [],
            }
            for index in range(count)
        ],
    }
    return {
        "status": "completed",
        "model": "fixture-model-version",
        "usage": {"input_tokens": 100, "output_tokens": 75},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(response)}]}],
    }


def test_dry_run_prints_the_prompt_without_credentials_or_network(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    def unexpected_client(**kwargs):
        pytest.fail("Dry run must not create a network client")

    monkeypatch.setattr("media_rag_bench.cli.httpx.Client", unexpected_client)
    assert main(["recommend", "movies", "Quiet science fiction", "--count", "2", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert movie_instructions(2) in output
    assert "Quiet science fiction" in output
    assert "no API request sent" in output


@pytest.mark.parametrize("use_case", [False, True])
def test_recommendation_cli_sends_the_displayed_prompt_and_renders_readable_answers(
    use_case, mock_openai, capsys
):
    prompt = "Quiet science fiction"
    args = ["recommend", "movies", prompt, "--count", "2"]
    if use_case:
        cases = json.loads((ROOT / "benchmarks/cases/movies.v1.json").read_bytes())
        prompt = cases[1]["prompt"]
        args = ["recommend", "movies", "--case", cases[1]["case_id"]]

    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer fixture-key"
        body = json.loads(request.content)
        assert body["model"] == "fixture-model"
        assert body["input"] == prompt
        assert body["instructions"] == movie_instructions(2)
        assert body["store"] is False
        assert "tools" not in body
        schema = body["text"]["format"]["schema"]
        assert body["text"]["format"]["strict"] is True
        assert set(schema["required"]) == set(schema["properties"])
        movie_schema = schema["$defs"]["Recommendation"]
        assert set(movie_schema["required"]) == set(movie_schema["properties"])
        assert movie_schema["additionalProperties"] is False
        assert schema["properties"]["recommendations"]["minItems"] == 2
        return httpx.Response(200, json=completed_response())

    mock_openai(handler)
    assert main(args) == 0
    output = capsys.readouterr().out
    assert prompt in output
    assert "1. Fictional Film 1 (2005)" in output
    assert "2. Fictional Film 2 (2005)" in output
    assert "An original fixture explanation" in output
    assert "Model: fixture-model-version" in output
    assert "Tokens: input 100, output 75" in output
    assert "fixture-key" not in output


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("refusal", "declined"),
        ("incomplete", "did not complete"),
        ("invalid", "invalid recommendation"),
        ("auth", "authentication or access failed"),
        ("timeout", "Could not reach OpenAI"),
    ],
)
def test_generation_failures_are_reported_without_success_or_credentials(
    failure, message, mock_openai, capsys
):
    def handler(request):
        if failure == "auth":
            return httpx.Response(401, json={"error": "fixture-key"})
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture-key", request=request)
        payload = completed_response()
        if failure == "incomplete":
            payload["status"] = "incomplete"
        else:
            payload["output"][0]["content"] = (
                [{"type": "refusal", "refusal": "Declined"}]
                if failure == "refusal" else [{"type": "output_text", "text": "not JSON"}]
            )
        return httpx.Response(200, json=payload)

    mock_openai(handler)
    assert main(["recommend", "movies", "Quiet science fiction", "--count", "2"]) == 1
    captured = capsys.readouterr()
    assert message in captured.err
    assert "fixture-key" not in captured.err
    assert "Movie recommendations" not in captured.out
