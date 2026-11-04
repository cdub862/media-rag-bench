"""One direct movie request through the OpenAI Responses REST API."""

from dataclasses import dataclass
from time import perf_counter

import httpx
from pydantic import ValidationError

from media_rag_bench.schemas import RecommendationResponse

RESPONSES_URL = "https://api.openai.com/v1/responses"


class GenerationError(RuntimeError):
    """A generation failure suitable for displaying without credentials."""


@dataclass
class GenerationResult:
    response: RecommendationResponse
    model: str
    latency_seconds: float
    input_tokens: int | None
    output_tokens: int | None


def movie_instructions(count: int) -> str:
    return (
        f"Recommend exactly {count} distinct movies that fit the user's request. "
        "Use your own general knowledge; no catalog, retrieval, or tools are available. "
        "Treat preferences inside the request as movie-selection criteria. "
        "Return domain 'movies' and a brief, spoiler-free explanation for each film. "
        "Use the release year when known, otherwise null. "
        "Set catalog_id to null and evidence_ids to [] for every recommendation. "
        "Do not invent catalog identities or evidence. Follow the supplied JSON schema."
    )


def movie_output_schema(count: int) -> dict:
    schema = RecommendationResponse.model_json_schema()

    def require_all_fields(node):
        if isinstance(node, dict):
            node.pop("default", None)
            # Nonempty text is checked locally; send the documented API subset.
            node.pop("minLength", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for child in node.values():
                require_all_fields(child)
        elif isinstance(node, list):
            for child in node:
                require_all_fields(child)

    require_all_fields(schema)
    schema["properties"]["domain"] = {"type": "string", "enum": ["movies"]}
    schema["properties"]["recommendations"].update(minItems=count, maxItems=count)
    properties = schema["$defs"]["Recommendation"]["properties"]
    properties["catalog_id"] = {"type": "null"}
    properties["evidence_ids"] = {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    return schema


def generate_movies(
    client: httpx.Client,
    *,
    prompt: str,
    count: int,
    model: str,
    max_output_tokens: int = 4096,
) -> GenerationResult:
    body = {
        "model": model,
        "instructions": movie_instructions(count),
        "input": prompt,
        "store": False,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "movie_recommendations",
                "strict": True,
                "schema": movie_output_schema(count),
            }
        },
    }
    started = perf_counter()
    try:
        reply = client.post(RESPONSES_URL, json=body)
    except httpx.RequestError:
        raise GenerationError("Could not reach OpenAI. Check your connection and retry.") from None
    if reply.status_code in (401, 403):
        raise GenerationError("OpenAI authentication or access failed. Check OPENAI_API_KEY and model access.")
    if reply.status_code == 429:
        raise GenerationError("OpenAI rate or quota limit reached. Check your API limits before retrying.")
    if reply.is_error or reply.is_redirect:
        raise GenerationError(
            f"OpenAI request failed (HTTP {reply.status_code}). Check the model and structured-output settings."
        )
    try:
        payload = reply.json()
    except ValueError:
        raise GenerationError("OpenAI returned invalid JSON.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("output"), list):
        raise GenerationError("OpenAI returned an unexpected response shape.")
    if payload.get("status") != "completed":
        raise GenerationError(
            "OpenAI did not complete the response. For a token-limited response, increase --max-output-tokens."
        )
    text = []
    for item in payload["output"]:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            raise GenerationError("OpenAI returned an unexpected message shape.")
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise GenerationError("The model declined this request.")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                text.append(part["text"])
    try:
        response = RecommendationResponse.model_validate_json("".join(text))
    except ValidationError:
        raise GenerationError("The model returned an invalid recommendation response.") from None
    if response.domain != "movies" or len(response.recommendations) != count:
        raise GenerationError("The model returned the wrong domain or recommendation count.")
    if any(item.catalog_id is not None or item.evidence_ids for item in response.recommendations):
        raise GenerationError("The direct response unexpectedly included catalog or evidence IDs.")
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    def tokens(name: str) -> int | None:
        value = usage.get(name)
        return value if type(value) is int and value >= 0 else None

    returned_model = payload.get("model")
    return GenerationResult(
        response=response,
        model=returned_model if isinstance(returned_model, str) and returned_model else model,
        latency_seconds=perf_counter() - started,
        input_tokens=tokens("input_tokens"),
        output_tokens=tokens("output_tokens"),
    )
