"""Unit tests for the redaction engine.

The `pii` layer is LLM-backed, so these tests stub the OpenAI call
(`openai_redactor.detect_pii_entities`) with canned entities and assert
the service maps spans -> offsets -> `[REDACTED:TYPE]` correctly. The
`secrets` and `glossary` layers are deterministic regex and are tested
against real input.
"""

from app.repo import openai_redactor
from app.repo.openai_redactor import PiiEntity
from app.service.redaction import redact_segment
from app.types.glossary import Glossary, GlossaryTerm

_PII_PATH = "app.service.redaction_detectors.openai_redactor.detect_pii_entities"


def _stub_pii(monkeypatch, entities: list[PiiEntity]):
    async def _impl(_text: str) -> list[PiiEntity]:
        return entities

    monkeypatch.setattr(_PII_PATH, _impl)


async def test_pii_entity_redacted(monkeypatch):
    _stub_pii(
        monkeypatch,
        [PiiEntity(text="John Smith", type="name", severity="high")],
    )
    result = await redact_segment(
        "please call John Smith back", segment_index=0, modes=["pii"]
    )
    assert "[REDACTED:NAME]" in result.redacted_text
    assert "John Smith" not in result.redacted_text
    name = [d for d in result.detections if d.type == "name"]
    assert name and name[0].severity == "high"
    assert name[0].detector == "pii"


async def test_pii_spoken_email_redacted(monkeypatch):
    # The model returns the natural-language span verbatim; we anchor it.
    _stub_pii(
        monkeypatch,
        [PiiEntity(text="john at example dot com", type="email", severity="medium")],
    )
    result = await redact_segment(
        "reach me at john at example dot com thanks",
        segment_index=0,
        modes=["pii"],
    )
    assert "[REDACTED:EMAIL]" in result.redacted_text
    assert "john at example dot com" not in result.redacted_text


async def test_pii_all_occurrences_redacted(monkeypatch):
    _stub_pii(
        monkeypatch,
        [PiiEntity(text="Acme Corp", type="name", severity="medium")],
    )
    result = await redact_segment(
        "Acme Corp called, then Acme Corp emailed",
        segment_index=0,
        modes=["pii"],
    )
    assert result.redacted_text.count("[REDACTED:NAME]") == 2


async def test_pii_unlocatable_span_dropped(monkeypatch):
    # If the model paraphrases and the span isn't in the text, we cannot
    # anchor an offset, so nothing is redacted (no crash).
    _stub_pii(
        monkeypatch,
        [PiiEntity(text="not present here", type="name", severity="high")],
    )
    result = await redact_segment(
        "an ordinary sentence", segment_index=0, modes=["pii"]
    )
    assert result.redacted_text == "an ordinary sentence"
    assert result.detections == []


async def test_pii_fails_open_on_empty(monkeypatch):
    _stub_pii(monkeypatch, [])
    result = await redact_segment(
        "my name is whoever", segment_index=0, modes=["pii"]
    )
    assert result.redacted_text == "my name is whoever"
    assert result.detections == []


async def test_secrets_aws_and_github():
    text = "aws is AKIAABCDEFGHIJKLMNOP and gh is ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    out = await redact_segment(text, segment_index=0, modes=["secrets"])
    types = {d.type for d in out.detections}
    assert "aws_access_key" in types
    assert "github_pat" in types
    expected_label = "[REDACTED:" + "_".join(["AWS", "ACCESS", "KEY"]) + "]"
    assert expected_label in out.redacted_text


async def test_glossary_case_insensitive():
    g = Glossary(terms=[GlossaryTerm(term="Acme", severity="medium")])
    out = await redact_segment(
        "ACME and acme and AcMe should all match",
        segment_index=0,
        modes=["glossary"],
        glossary=g,
    )
    assert out.redacted_text.count("[REDACTED:GLOSSARY:ACME]") == 3


async def test_secrets_mode_does_not_invoke_pii(monkeypatch):
    # When `pii` is not requested, the LLM is never called.
    async def _boom(_text: str):
        raise AssertionError("PII layer must not run for secrets-only mode")

    monkeypatch.setattr(_PII_PATH, _boom)
    out = await redact_segment(
        "akey AKIAABCDEFGHIJKLMNOP", segment_index=0, modes=["secrets"]
    )
    types = {d.type for d in out.detections}
    assert "aws_access_key" in types


async def test_no_modes_no_redactions():
    out = await redact_segment("alex@example.com", segment_index=0, modes=[])
    assert out.redacted_text == "alex@example.com"
    assert out.detections == []


def test_parse_entities_drops_malformed():
    # Repo-level guard: untrusted model JSON is sanitized.
    parsed = openai_redactor._parse_entities(
        {
            "entities": [
                {"text": "Jane Doe", "type": "name", "severity": "high"},
                {"text": "", "type": "name", "severity": "high"},  # empty
                {"type": "name", "severity": "high"},  # no text
                {"text": "weird", "type": 123, "severity": "nope"},  # coerced
                "garbage",
            ]
        }
    )
    assert [(e.text, e.type, e.severity) for e in parsed] == [
        ("Jane Doe", "name", "high"),
        ("weird", "other", "medium"),
    ]
