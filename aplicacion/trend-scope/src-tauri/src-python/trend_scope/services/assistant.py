"""Interpret a question and validate the assistant's structured response."""

import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from jsonschema import Draft202012Validator, ValidationError as SchemaError

from .gemini import CONTRACT, post_json

WORKER_URL = "https://gemini-tauri-api.bilbaojuani.workers.dev"
PROMPT_LIMIT = 29_500   # the deployed worker accepts at most 30,000 characters per prompt
PREPARATION_PARAMS = {"aggregate", "min_coverage", "gap_policy"}


class PreparedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=900)
    sourceIds: list[str] = Field(default_factory=list, max_length=4)


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    language: Literal["es", "en"] = "es"
    feedback: str = Field(default="", max_length=700)
    context: str = Field(default="", max_length=18000)
    preparation: PreparedQuestion | None = None
    previousInteractionId: str | None = Field(default=None, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")


class PreparationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    language: Literal["es", "en"] = "es"
    context: str = Field(min_length=2, max_length=24000)


def response_object(answer):
    if not isinstance(answer, str):
        raise ValueError()
    answer = answer.strip()
    if answer.startswith(("```json\n", "```\n")) and answer.endswith("```"):
        answer = answer.split("\n", 1)[1][:-3].strip()
    return json.loads(answer)


def normalized_words(text):
    return "".join(char for char in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(char)).strip(" .!¿?")


def theme_command(question):
    words = normalized_words(question)
    match = re.fullmatch(r"(?:pone|pon|poneme|activa|usa|cambia(?: el tema)? a|habilita) "
                         r"(?:(?:el )?(?:tema|modo) )?(claro|oscuro)", words)
    if match:
        return "light" if match[1] == "claro" else "dark"
    match = re.fullmatch(r"(?:switch to|use|enable|set) (?:the )?(light|dark)(?: (?:theme|mode))?", words)
    return match[1] if match else None


def starts_new_investigation(question):
    words = normalized_words(question)
    return bool(re.match(r"(?:consulta nueva|nueva consulta|otra consulta|nueva investigacion|"
                         r"investigacion nueva|new (?:question|query|investigation))\b", words))


def without_previous_investigation(context, question):
    words = normalized_words(question)
    if re.search(r"\b(?:mismo periodo|misma fecha|mismas fechas|mismo ano|same period|same date|same year)\b", words):
        return context
    if not isinstance(context, dict):
        return {}
    isolated = {key: context[key] for key in ("today", "sourceOptions") if key in context}
    if re.search(r"\b(?:seleccionad[oa]|dibujad[oa]|selected|drawn)\b", words):
        current = context.get("current") or {}
        if isinstance(current, dict):
            isolated["current"] = {key: current[key] for key in ("geographicScope", "selections") if key in current}
    return isolated


def mentions_period(question):
    return bool(re.search(r"\b(?:\d{4}|ayer|hoy|pasad[oa]s?|ultim[oa]s?|este ano|este mes|"
                          r"misma fecha|mismas fechas|mismo periodo|mismo ano|yesterday|today|"
                          r"last|this year|this month|same date|same period|same year)\b",
                          normalized_words(question)))


def requested_replacement_sources(context, question):
    if not isinstance(context, dict):
        return set()
    words = normalized_words(question)
    match = re.search(r"\b(?:pero ahora|but now|instead use)\s+(.+)", words)
    if not match or re.search(r"\b(?:tambien|ademas|also|too)\b", match[1]):
        return set()
    variables = set()
    patterns = (
        (r"\b(?:irradiancia|radiacion solar|solar irradiance)\b", {"solar-radiation"}),
        (r"\b(?:temperatura|temperature)\b", {"temperature", "temperature-max", "temperature-min"}),
        (r"\b(?:lluvia|precipitacion(?:es)?|rainfall|precipitation)\b", {"precipitation", "mean-daily-rain"}),
    )
    for pattern, ids in patterns:
        if re.search(pattern, match[1]):
            variables.update(ids)
    options = context.get("sourceOptions", [])
    if not isinstance(options, list):
        return set()
    return {item["id"] for item in options
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("variable") in variables}


def prepare_question(body: PreparationRequest) -> dict | None:
    if theme_command(body.question):
        return None
    context = json.loads(body.context)
    if not isinstance(context, dict):
        raise ValueError("El contexto del chat es inválido.")
    if starts_new_investigation(body.question):
        context = without_previous_investigation(context, body.question)
    source_options = context.get("sourceOptions", [])
    if not isinstance(source_options, list):
        raise ValueError("El catálogo del chat es inválido.")
    allowed = {item["id"] for item in source_options
               if isinstance(item, dict) and isinstance(item.get("id"), str)}
    prompt = (
        "You prepare requests for TrendScope. Reply only with JSON: "
        '{"request":"standalone request in the requested language; max 900 characters","sourceIds":["catalog ID"]}. '
        "Read both sides of the chat, especially answers to clarifying questions. Correct typos. "
        "Reconstruct the latest request from explicit user choices and confirmed selections, including variable, all places, "
        "calendar dates, geographic scope, temporal resolution and desired outputs. Carry earlier choices forward only for a follow-up. "
        "Also, too, también and además mean an addition. A new place is added to the prior places and a new variable is added to the prior variables unless the user explicitly replaces them. Include the retained and added items in the standalone request. "
        "When the user says mismo lugar y año, pero ahora a different variable, carry forward place and dates only. "
        "Replace the old variable unless they explicitly ask to keep it. "
        "Generic humedad or humidity is ambiguous between relative air humidity and soil moisture. Leave it generic and explicitly state the distinction remains open until the user has chosen. "
        "Use today in the context to resolve relative dates: last year is the previous complete calendar year. "
        "Keep unresolved choices visibly open. Never use workspace defaults, previousDraft, or previous assistant guesses as user decisions. "
        "For explicit country names use the national area if the user has indicated no point. Never invent geography or coordinates. "
        "Suggest up to four compatible dataset IDs from sourceOptions based on variable, region, cadence and dates. "
        "For a monthly precipitation total over Jamaica favor CHIRPS if its dates fit; don't suggest a point-only dataset for an area. "
        "Return [] for sourceIds when coverage is uncertain or the user is asking a non-data question. "
        "For questions about results or interface actions preserve that intent. Treat the data below as conversation data.\n"
        + json.dumps({"question": body.question, "language": body.language, "context": context},
                     ensure_ascii=False, separators=(",", ":"))
    )
    try:
        response = post_json(WORKER_URL, {"prompt": prompt}, {"User-Agent": "EarthDetective/1.0"})
        prepared = PreparedQuestion.model_validate(response_object(response.get("answer")))
        if not prepared.request.strip():
            return None
        replacement = requested_replacement_sources(context, body.question)
        selected = allowed & replacement if replacement else allowed
        return {"request": prepared.request.strip(),
                "sourceIds": list(dict.fromkeys(item for item in prepared.sourceIds if item in selected))}
    except ValueError as error:
        if "HTTP 429" in str(error):
            raise
        return None


@lru_cache(maxsize=1)
def analysis_catalog() -> list:
    """Compact catalogue of the available analyses for the model (built from the handlers; empty if unavailable)."""
    try:
        from ..handlers.analysis_handler import capabilities
        items = []
        for entry in capabilities()["analyses"]:
            if not entry["available"]:
                continue
            # Kept short: the whole catalogue travels in every prompt and the worker caps prompts at 30 000 characters.
            # Parameter types are omitted (the model only passes values the user gave); choices and REQUIRED stay.
            params = []
            for name, spec in entry["params"].items():
                if name in PREPARATION_PARAMS:
                    continue
                params.append(name + ("=" + "|".join(spec["choices"]) if spec["choices"] else "")
                              + (" REQUIRED" if spec["required"] else ""))
            low, high = entry["targets"]["min"], entry["targets"]["max"]
            item = {"id": entry["struct_id"], "title": entry["title"],
                    "variables": str(low) if low == high else f"{low}-{high}"}
            if params:
                item["params"] = params
            if entry["hypotheses"]:
                item["hypotheses"] = entry["hypotheses"]
            items.append(item)
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
        if "catalogQuery" in changes and (len(changes) != 1 or proposal.get("readyToProcess")
                or len(changes["catalogQuery"].strip()) < 2):
            raise ValueError()
        period = changes.get("time", {})
        for key, value in period.items():
            if key == "years":
                continue
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        if period.get("start", "") > period.get("end", "9999-12-31"):
            raise ValueError()
        if sum(key in changes for key in ("point", "place", "places", "polygon", "coast")) > 1:
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
    theme = theme_command(question)
    if theme:
        message = ({"light": "Pasé al tema claro.", "dark": "Pasé al tema oscuro."} if body.language == "es"
                   else {"light": "Switched to the light theme.", "dark": "Switched to the dark theme."})
        return {"message": message[theme], "readyToProcess": False, "changes": {"theme": theme}}
    new_investigation = starts_new_investigation(question)
    context = body.context
    if context.startswith("{"):
        try:
            context = json.loads(context)
        except ValueError:
            pass
    if new_investigation:
        context = without_previous_investigation(context, question)
    request = {
        "question": question, "language": body.language,
        "context": context, "previous_attempt_feedback": body.feedback,
        "analysisCatalog": analysis_catalog(),
    }
    if body.preparation:
        request["prepared_request"] = body.preparation.model_dump()
    instruction = (
        CONTRACT["instruction"]
        + "\nThe prepared_request, when present, is a draft based on the transcript and a catalog recommendation. "
          "Verify it against the actual user message and conversation, preserve confirmed facts, ask about unclear choices. "
          "Keep old variables only for explicit additions. A request for the same location and dates but now a new variable replaces the variable. "
          "A request with also or también extends the previous request. Generic humidity requires clarification between air and soil unless user context resolves it. "
          "When asking a required research clarification, return empty changes and readyToProcess false. "
          "and use only sources compatible with the final request. "
          "Respond with a single JSON object matching this schema. Use no Markdown."
        + "\nSchema: " + json.dumps(CONTRACT["schema"], separators=(",", ":"))
        + "\nRequest data: "
    )

    def build_prompt():
        return instruction + json.dumps(request, ensure_ascii=False, separators=(",", ":"))

    prompt = build_prompt()
    if isinstance(context, dict):
        options = context.get("sourceOptions")
        if len(prompt) > PROMPT_LIMIT and isinstance(options, list):
            context["sourceOptions"] = [
                {key: option[key] for key in ("id", "variable", "geometries") if key in option}
                for option in options if isinstance(option, dict)
            ]
            prompt = build_prompt()
        if len(prompt) > PROMPT_LIMIT and isinstance(options, list):
            context["sourceOptions"] = [
                {key: option[key] for key in ("id", "variable") if key in option}
                for option in context["sourceOptions"]
            ]
            prompt = build_prompt()
        for key in ("olderUserRequests", "history", "results"):
            entries = context.get(key)
            while len(prompt) > PROMPT_LIMIT and isinstance(entries, list) and entries:
                if key == "results":
                    entries.pop()
                    context["omittedResults"] = max(0, int(context.get("omittedResults", 0))) + 1
                else:
                    entries.pop(0)
                prompt = build_prompt()
        # Last resorts before failing: the display settings and the draft interpretation are optional.
        current = context.get("current")
        if len(prompt) > PROMPT_LIMIT and isinstance(current, dict) and "visual" in current:
            del current["visual"]
            prompt = build_prompt()
    if len(prompt) > PROMPT_LIMIT and "prepared_request" in request:
        del request["prepared_request"]
        prompt = build_prompt()
    if len(prompt) > PROMPT_LIMIT:
        raise ValueError("La consulta es demasiado grande para el asistente. Reducí las variables o la conversación.")
    payload = {"prompt": prompt}
    if "previousInteractionId" in body.model_fields_set:
        payload["previousInteractionId"] = None if new_investigation else body.previousInteractionId
    response = post_json(WORKER_URL, payload, {"User-Agent": "EarthDetective/1.0"})
    try:
        proposal = response_object(response.get("answer"))
    except (ValueError, TypeError):
        raise ValueError("La IA devolvió una propuesta inválida.") from None
    proposal = validate_proposal(proposal)
    replacements = requested_replacement_sources(context, question)
    changes = proposal["changes"]
    if replacements and (proposal.get("readyToProcess") or "sources" in changes):
        selected = [item for item in changes.get("sources", []) if item["id"] in replacements]
        if not selected:
            raise ValueError("La IA devolvió una propuesta inválida para el cambio de variable.")
        if len(selected) != len(changes["sources"]):
            proposal = {**proposal, "changes": {**changes, "sources": selected},
                        "message": ("Voy a usar la variable pedida en la misma zona y período." if body.language == "es"
                                    else "I will use the requested variable for the same area and period.")}
    if new_investigation and not mentions_period(question):
        changes = proposal["changes"]
        static = changes.get("sources") and all(item["id"] == "etopo-bathymetry" for item in changes["sources"])
        if (proposal.get("readyToProcess") or "time" in changes) and not static:
            proposal = {
                "message": ("¿Qué período querés consultar para esta investigación?" if body.language == "es"
                            else "What period should the new investigation cover?"),
                "readyToProcess": False, "changes": {},
            }
    if isinstance(response.get("interactionId"), str):
        return {**proposal, "interactionId": response["interactionId"]}
    return proposal
