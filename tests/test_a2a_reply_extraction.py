"""Unit tests for A2A reply extraction helpers."""

from __future__ import annotations

import json

from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TextPart,
)

from procu_forge_buyer.a2a_client import (
    _select_envelope,
    _text_from_part,
    _texts_from_task,
    extract_reply_from_task_event,
)

_SAMPLE_ENVELOPE = {
    "message_id": "msg-1",
    "rfq_id": "rfq-1",
    "vendor_id": "vendor-1",
    "from_agent": "vendor_agent",
    "to_agent": "buyer_agent",
    "message_type": "QUOTE",
    "round": 0,
    "timestamp": "2026-06-03T10:00:00Z",
    "payload": {"unit_price": 30.88},
}

_COUNTER_ENVELOPE = {
    **_SAMPLE_ENVELOPE,
    "message_id": "msg-2",
    "message_type": "COUNTER_OFFER",
}


def _text_part(text: str) -> Part:
    return Part(root=TextPart(text=text))


def _data_part(data: dict, *, function_response: bool = False) -> Part:
    metadata = {"adk/type": "function_response"} if function_response else None
    return Part(root=DataPart(data=data, metadata=metadata))


def test_text_from_part_text_part():
    part = _text_part(json.dumps(_SAMPLE_ENVELOPE))
    assert _text_from_part(part) == json.dumps(_SAMPLE_ENVELOPE)


def test_text_from_part_data_part_envelope():
    part = _data_part(_SAMPLE_ENVELOPE)
    text = _text_from_part(part)
    assert text is not None
    assert json.loads(text) == _SAMPLE_ENVELOPE


def test_text_from_part_function_response_nested():
    part = _data_part(
        {"response": json.dumps(_SAMPLE_ENVELOPE)},
        function_response=True,
    )
    text = _text_from_part(part)
    assert text == json.dumps(_SAMPLE_ENVELOPE)


def test_texts_from_task_empty_status_populated_artifacts():
    """Reproduces ADK success path: final content in artifacts, not status.message."""
    envelope_json = json.dumps(_SAMPLE_ENVELOPE)
    task = Task(
        id="task-1",
        context_id="rfq-1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=[
            Artifact(artifact_id="art-1", parts=[_text_part(envelope_json)]),
        ],
    )
    texts = _texts_from_task(task)
    assert envelope_json in texts
    assert _select_envelope(texts) == envelope_json


def test_select_envelope_prefers_last_valid_envelope():
    candidates = [
        json.dumps(_SAMPLE_ENVELOPE),
        json.dumps(_COUNTER_ENVELOPE),
        "not json",
    ]
    assert _select_envelope(candidates) == json.dumps(_COUNTER_ENVELOPE)


def test_select_envelope_falls_back_to_last_non_empty():
    assert _select_envelope(["", "plain ack"]) == "plain ack"


def test_select_envelope_empty_when_no_candidates():
    assert _select_envelope([]) == ""


def test_extract_reply_from_task_event_artifact_update():
    envelope_json = json.dumps(_SAMPLE_ENVELOPE)
    task = Task(
        id="task-1",
        context_id="rfq-1",
        status=TaskStatus(state=TaskState.working),
    )
    update = TaskArtifactUpdateEvent(
        task_id="task-1",
        context_id="rfq-1",
        artifact=Artifact(
            artifact_id="art-1",
            parts=[_text_part(envelope_json)],
        ),
        last_chunk=True,
    )
    candidates = extract_reply_from_task_event(task, update)
    assert _select_envelope(candidates) == envelope_json


def test_extract_reply_from_task_event_status_message():
    envelope_json = json.dumps(_SAMPLE_ENVELOPE)
    task = Task(
        id="task-1",
        context_id="rfq-1",
        status=TaskStatus(
            state=TaskState.completed,
            message=Message(
                message_id="m1",
                role="agent",
                parts=[_text_part(envelope_json)],
            ),
        ),
    )
    candidates = extract_reply_from_task_event(task, None)
    assert _select_envelope(candidates) == envelope_json
