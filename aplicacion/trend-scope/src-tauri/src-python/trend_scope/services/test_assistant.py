import json
from datetime import date

import pytest

from trend_scope.services import assistant
from trend_scope.services.coverage import CoverageRequest, coverage


@pytest.mark.parametrize(("scope", "expected"), [
    ("land", ("compatible", "catalog")),
    ("area", ("incompatible", "area")),
    ("sea", ("incompatible", "land_only")),
])
def test_argentine_soil_moisture(scope, expected):
    request = CoverageRequest(variable="soil-moisture", start="2000-01-01", end="2025-12-31", scope=scope)
    matches = coverage(request, today=date(2026, 11, 14))
    assert len(matches) == 2
    assert {(row["status"], row["reason"]) for row in matches} == {expected}


def test_partial_period_and_unverified_station():
    request = CoverageRequest(variable="solar-radiation", start="1980-01-01", end="2025-12-31", scope="land")
    point = next(row for row in coverage(request, date(2026, 11, 14)) if row["access"] == "nasa.power.monthly")
    assert point["status"] == "partial"
    request = CoverageRequest(variable="precipitation", start="2000-01-01", end="2025-12-31", scope="station")
    station = next(row for row in coverage(request) if row["selection"] == "Station")
    assert station["status"] == "unverified"


def test_proxy_interpretation_validates_response_without_local_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def response(url, body, headers):
        assert url == assistant.WORKER_URL
        assert set(body) == {"prompt"}
        request = json.loads(body["prompt"].split("\nRequest data: ", 1)[1])
        assert request["question"] == "Humedad en San Luis"
        assert request["context"] == "previous turns"
        return {"answer": json.dumps({"message": "¿Humedad del aire o del suelo?", "changes": {}})}

    monkeypatch.setattr(assistant, "post_json", response)
    result = assistant.interpret(assistant.AssistantQuestion(
        question="Humedad en San Luis", context="previous turns"
    ))
    assert result["changes"] == {}


def test_multiple_places_contract():
    proposal = {"message": "Buscaré las localidades.", "changes": {"places": [
        {"name": "San Luis, San Luis, Argentina", "kind": "localidades"},
        {"name": "El Volcán, San Luis, Argentina", "kind": "localidades"},
    ]}}
    assert assistant.validate_proposal(proposal) == proposal
    with pytest.raises(ValueError):
        assistant.validate_proposal({"message": "x", "changes": {"places": []}})
    with pytest.raises(ValueError):
        assistant.validate_proposal({"message": "x", "changes": {
            **proposal["changes"], "point": {"longitude": -66, "latitude": -33}}})


def test_geocoder_prefers_town_over_duplicate_boundaries(monkeypatch):
    from trend_scope.services import public_sources
    def feature(key, osm_id, state="San Luis"):
        return {"properties": {"name": "San Luis", "state": state, "country": "Argentina",
                "osm_key": key, "osm_type": "R", "osm_id": osm_id},
                "geometry": {"type": "Point", "coordinates": [-66.33, -33.3]}}
    monkeypatch.setattr(public_sources, "request_json", lambda *args, **kwargs: ({"features": [
        feature("place", 1), feature("boundary", 2), feature("boundary", 3),
        feature("place", 4, "Salta")
    ]}, "test"))
    found = public_sources.find_world_cities("San Luis, San Luis, Argentina", "es")
    assert [item["id"] for item in found] == ["R1", "R4"]


def test_proxy_receives_feedback_when_correcting_a_proposal(monkeypatch):
    def response(url, body, headers):
        request = json.loads(body["prompt"].split("\nRequest data: ", 1)[1])
        assert request["question"] == "Radiación solar"
        assert request["previous_attempt_feedback"] == "Correct the invalid proposal."
        return {"answer": "```json\n" + json.dumps({"message": "¿Qué período querés consultar?", "changes": {}}) + "\n```"}

    monkeypatch.setattr(assistant, "post_json", response)
    result = assistant.interpret(assistant.AssistantQuestion(
        question="Radiación solar", feedback="Correct the invalid proposal.",

    ))
    assert result["changes"] == {}

def test_catalog_discovery_continues_after_empty_and_stops_after_match(monkeypatch):
    from trend_scope.services import downloads
    calls = []

    def request(url, provider, **params):
        calls.append(provider)
        if provider == "NASA Earthdata":
            return {"feed": {"entry": []}}, url
        return {"items": [{"id": "usgs-test", "title": "Regional snow observations"}]}, url

    monkeypatch.setattr(downloads, "request_json", request)
    found = downloads.search_collections("snow")
    assert calls == ["NASA Earthdata", "USGS ScienceBase"]
    assert [step["status"] for step in found["attempts"]] == ["empty", "found"]
    assert found["collections"][0]["provider"] == "USGS ScienceBase"


def test_search_proposal_cannot_run_acquisition():
    proposal = {"message": "Busco nieve.", "changes": {"catalogQuery": "snow depth"}}
    assert assistant.validate_proposal({**proposal, "readyToProcess": False})
    with pytest.raises(ValueError):
        assistant.validate_proposal({**proposal, "readyToProcess": True})


def test_proxy_threads_a_validated_interaction_id(monkeypatch):
    def response(url, body, headers):
        assert body["previousInteractionId"] == "v1_previous"
        return {
            "answer": json.dumps({"message": "Uso las mismas regiones.", "changes": {}}),
            "interactionId": "v1_next",
        }

    monkeypatch.setattr(assistant, "post_json", response)
    result = assistant.interpret(assistant.AssistantQuestion(
        question="En el periodo 1994 a 2010", previousInteractionId="v1_previous",
    ))
    assert result["interactionId"] == "v1_next"



def test_preparation_reads_the_transcript_and_passes_only_catalog_suggestions(monkeypatch):
    calls = []

    def response(url, body, headers):
        assert url == assistant.WORKER_URL
        calls.append(body)
        if len(calls) == 1:
            sent = json.loads(body["prompt"].split("\n", 1)[1])
            assert sent["context"]["today"] == "2026-11-15"
            assert sent["context"]["history"][0]["text"] == "Precipitaciones de Jamaica"
            assert sent["context"]["history"][-1]["text"] == "Promedios por mes"
            assert sent["question"] == "del año pasado"
            return {"answer": json.dumps({
                "request": "Precipitaciones de Jamaica durante 2025, mes a mes.",
                "sourceIds": ["invented", "chirps-monthly-precipitation", "chirps-monthly-precipitation"],
            })}
        sent = json.loads(body["prompt"].split("\nRequest data: ", 1)[1])
        assert sent["question"] == "del año pasado"
        assert sent["prepared_request"]["sourceIds"] == ["chirps-monthly-precipitation"]
        assert "2025" in sent["prepared_request"]["request"]
        return {"answer": json.dumps({"message": "Buscaré las precipitaciones de Jamaica.", "changes": {}})}

    monkeypatch.setattr(assistant, "post_json", response)
    context = json.dumps({"today": "2026-11-15", "history": [
        {"role": "user", "text": "Precipitaciones de Jamaica"},
        {"role": "assistant", "text": "¿Con qué frecuencia?"},
        {"role": "user", "text": "Promedios por mes"},
    ], "sourceOptions": [{"id": "chirps-monthly-precipitation"}]})
    preparation = assistant.prepare_question(assistant.PreparationRequest(question="del año pasado", context=context))
    result = assistant.interpret(assistant.AssistantQuestion(
        question="del año pasado", context=context, preparation=preparation,
    ))
    assert result["changes"] == {}


def test_preparation_failure_leaves_interpretation_available(monkeypatch):
    def unavailable(*args):
        raise ValueError("Servicio de IA devolvió HTTP 503.")

    monkeypatch.setattr(assistant, "post_json", unavailable)
    assert assistant.prepare_question(assistant.PreparationRequest(question="Jamaica", context="{}")) is None



def test_visual_command_does_not_send_a_weather_request(monkeypatch):
    def unexpected(*args):
        pytest.fail("A local appearance change must not use Gemini quota")

    monkeypatch.setattr(assistant, "post_json", unexpected)
    question = "Poné el tema claro"
    assert assistant.prepare_question(assistant.PreparationRequest(question=question, context="{}")) is None
    result = assistant.interpret(assistant.AssistantQuestion(question=question, context="{}"))
    assert result["changes"] == {"theme": "light"}
    assert result["readyToProcess"] is False


def test_explicit_new_investigation_does_not_inherit_old_date(monkeypatch):
    context = json.dumps({
        "today": "2026-11-15", "current": {"time": {"start": "2025-01-01"}},
        "history": [{"role": "user", "text": "2025 en Jamaica"}],
    })

    def response(url, body, headers):
        assert body["previousInteractionId"] is None
        request = json.loads(body["prompt"].split("\nRequest data: ", 1)[1])
        assert request["context"] == {"today": "2026-11-15"}
        return {"answer": json.dumps({"message": "Consulto 2025.", "readyToProcess": True, "changes": {
            "time": {"start": "2025-01-01", "end": "2025-12-31"},
        }})}

    monkeypatch.setattr(assistant, "post_json", response)
    result = assistant.interpret(assistant.AssistantQuestion(
        question="Consulta nueva: temperatura de Tucumán", context=context, previousInteractionId="v1_old",
    ))
    assert result["changes"] == {}
    assert result["readyToProcess"] is False
    assert "período" in result["message"]


def test_preparation_exposes_shared_rate_limit_without_second_request(monkeypatch):
    def limited(*args):
        raise ValueError("Servicio de IA devolvió HTTP 429.")

    monkeypatch.setattr(assistant, "post_json", limited)
    with pytest.raises(ValueError, match="HTTP 429"):
        assistant.prepare_question(assistant.PreparationRequest(question="Jamaica", context="{}"))



def test_explicit_variable_switch_keeps_geography_but_drops_old_variable(monkeypatch):
    context = json.dumps({"sourceOptions": [
        {"id": "power-solar-area", "variable": "solar-radiation"},
        {"id": "chirps-monthly-precipitation", "variable": "precipitation"},
    ]})

    def response(*args):
        return {"answer": json.dumps({
            "message": "Consultaré irradiancia y lluvia en Jamaica.",
            "readyToProcess": True,
            "changes": {"sources": [
                {"id": "chirps-monthly-precipitation", "geometryId": "jm"},
                {"id": "power-solar-area", "geometryId": "jm"},
            ]},
        })}

    monkeypatch.setattr(assistant, "post_json", response)
    reply = assistant.interpret(assistant.AssistantQuestion(
        question="Mismo lugar y año, pero ahora irradiancia mensual.", context=context,
    ))
    assert reply["changes"]["sources"] == [{"id": "power-solar-area", "geometryId": "jm"}]
    assert "lluvia" not in reply["message"]
