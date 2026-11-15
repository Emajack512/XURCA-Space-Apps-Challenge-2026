"""Interpret a question and validate the assistant's structured response."""

import os
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from .gemini import CONTRACT, gemini_text, post_json


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    language: Literal["es", "en"] = "es"
    endpoint: Optional[str] = Field(default=None, max_length=512)
    context: str = Field(default="", max_length=18000)


class Interpretation(BaseModel):
    message: str = Field(min_length=1, max_length=2400)
    changes: dict


def interpret(body: AssistantQuestion) -> dict:
    question = body.question.strip()
    if not question:
        raise ValueError("Escribí una pregunta para el asistente.")
    prompt = {"question": question, "language": body.language, "context": body.context}
    try:
        if body.endpoint:
            uri = urlparse(body.endpoint)
            if uri.scheme != "https" or not uri.hostname or uri.username or uri.password:
                raise ValueError("El servicio del asistente requiere una URL HTTPS.")
            proposal = Interpretation.model_validate(post_json(body.endpoint, prompt))
        else:
            key = os.getenv("GEMINI_API_KEY", "").strip()
            if not key:
                raise ValueError("El asistente aún no tiene un servicio de Gemini configurado.")
            reply = gemini_text({
                "systemInstruction": {"parts": [{"text": CONTRACT["instruction"]}]},
                "contents": [{"role": "user", "parts": [{"text": (
                    f"Language: {body.language}\nContext: {body.context}\nLatest user message: {question}"
                )}]}],
                "generationConfig": {
                    "responseMimeType": "application/json", "responseJsonSchema": CONTRACT["schema"],
                    "maxOutputTokens": 1600,
                },
            }, key)
            proposal = Interpretation.model_validate_json(reply)
    except ValidationError:
        raise ValueError("El asistente devolvió una propuesta que no se pudo validar.") from None
    return proposal.model_dump(mode="json")
