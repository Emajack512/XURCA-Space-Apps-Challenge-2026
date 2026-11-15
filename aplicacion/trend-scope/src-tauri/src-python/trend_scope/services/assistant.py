"""Interpret a question and validate the assistant's structured response."""

import json
from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from jsonschema import Draft202012Validator, ValidationError as SchemaError

from .gemini import CONTRACT, post_json

WORKER_URL = "https://gemini-tauri-api.bilbaojuani.workers.dev"
PROMPT_LIMIT = 29_500   # the deployed worker accepts at most 30,000 characters per prompt
PREPARATION_PARAMS = {"aggregate", "min_coverage", "gap_policy"}


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    language: Literal["es", "en"] = "es"
    feedback: str = Field(default="", max_length=700)
    context: str = Field(default="", max_length=18000)


@lru_cache(maxsize=1)
def analysis_catalog() -> list:
    """Compact catalogue of the available analyses for the model (built from the handlers; empty if unavailable)."""
    try:
        from ..handlers.analysis_handler import capabilities
        items = []
        for entry in capabilities()["analyses"]:
            if not entry["available"]:
                continue
            params = {}
            for name, spec in entry["params"].items():
                if name in PREPARATION_PARAMS:
                    continue
                text = spec["type"] + ("[" + "|".join(spec["choices"]) + "]" if spec["choices"] else "")
                params[name] = text + (" REQUIRED" if spec["required"] else "")
            items.append({"id": entry["struct_id"], "title": entry["title"],
                          "variables": [entry["targets"]["min"], entry["targets"]["max"]],
                          "params": params, "hypotheses": entry["hypotheses"]})
        return items
    except Exception:  # the chat keeps working without analyses
        return []


def check_analysis(item: dict) -> None:
    """Dry-run the handlers' own validation of a proposed analysis (struct, targets, parameters, hypothesis)."""
    from ..handlers.analysis_handler import resolve
    from ..handlers.contracts import AnalysisSpec, HandlerError
    try:
        resolve(AnalysisSpec(id="proposal", struct=item["struct"], targets=item["targets"],
                             params=item.get("params") or {}, hypothesis=item.get("hypothesis")))
    except HandlerError as error:
        raise ValueError(f"La IA devolvió una propuesta inválida (análisis): {error.message}") from None
    except ValidationError as error:
        raise ValueError("La IA devolvió una propuesta inválida (análisis): " + "; ".join(
            f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}" for detail in error.errors()[:3])) from None


def validate_proposal(proposal):
    try:
        Draft202012Validator(CONTRACT["schema"]).validate(proposal)
        changes = proposal["changes"]
        period = changes.get("time", {})
        for value in period.values():
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        if period.get("start", "") > period.get("end", "9999-12-31"):
            raise ValueError()
        if sum(key in changes for key in ("point", "place", "places", "polygon")) > 1:
            raise ValueError()
        point = changes.get("point")
        if point and not (-180 <= point["longitude"] <= 180 and -90 <= point["latitude"] <= 90):
            raise ValueError()
        polygon = changes.get("polygon")
        if polygon is not None and (not 3 <= len(polygon) <= 100 or any(
            len(p) != 2 or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in polygon
        )):
            raise ValueError()
        json.dumps(proposal, allow_nan=False)
    except (SchemaError, ValueError, TypeError, KeyError):
        raise ValueError("La IA devolvió una propuesta inválida. No se aplicaron cambios; reformulá el pedido.") from None
    analysis = proposal["changes"].get("analysis")
    if analysis is not None:
        check_analysis(analysis)
    return proposal


def interpret(body: AssistantQuestion) -> dict:
    question = body.question.strip()
    if not question:
        raise ValueError("Escribí una pregunta para el asistente.")
    request = {
        "question": question, "language": body.language,
        "context": body.context, "previous_attempt_feedback": body.feedback,
        "analysisCatalog": analysis_catalog(),
    }
    prompt = (
        CONTRACT["instruction"]
        + "\nRespond with a single JSON object matching this schema. Use no Markdown."
        + "\nSchema: " + json.dumps(CONTRACT["schema"], separators=(",", ":"))
        + "\nRequest data: " + json.dumps(request, ensure_ascii=False, separators=(",", ":"))
    )
    if len(prompt) > PROMPT_LIMIT:
        raise ValueError("La consulta es demasiado grande para el asistente. Reducí las variables o la conversación.")
    answer = post_json(WORKER_URL, {"prompt": prompt}, {"User-Agent": "EarthDetective/1.0"}).get("answer")
    try:
        if not isinstance(answer, str):
            raise ValueError()
        answer = answer.strip()
        if answer.startswith(("```json\n", "```\n")) and answer.endswith("```"):
            answer = answer.split("\n", 1)[1][:-3].strip()
        proposal = json.loads(answer)
    except (ValueError, TypeError):
        raise ValueError("La IA devolvió una propuesta inválida.") from None
    return validate_proposal(proposal)
