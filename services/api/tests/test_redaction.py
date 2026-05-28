"""Unit tests for the three-layer redaction engine."""

from app.service.redaction import redact_segment
from app.types.glossary import Glossary, GlossaryTerm


def test_pii_email_detected():
    result = redact_segment(
        "ping me at alex@example.com later",
        segment_index=0,
        modes=["pii"],
    )
    assert "[REDACTED:EMAIL]" in result.redacted_text
    assert any(d.type == "email" for d in result.detections)
    assert all(d.severity in ("low", "medium", "high") for d in result.detections)


def test_pii_ssn_high_severity():
    result = redact_segment(
        "the ssn is 123-45-6789, ok?",
        segment_index=0,
        modes=["pii"],
    )
    assert "[REDACTED:SSN]" in result.redacted_text
    high = [d for d in result.detections if d.type == "ssn"]
    assert high and high[0].severity == "high"


def test_pii_credit_card_luhn_filtered():
    """A 16-digit string that doesn't pass Luhn is not redacted."""
    bad = "card number 1234 5678 9012 3456"  # fails Luhn
    out = redact_segment(bad, segment_index=0, modes=["pii"])
    assert "[REDACTED:CREDIT_CARD]" not in out.redacted_text

    good = "card number 4242 4242 4242 4242"  # passes Luhn
    out2 = redact_segment(good, segment_index=0, modes=["pii"])
    assert "[REDACTED:CREDIT_CARD]" in out2.redacted_text


def test_secrets_aws_and_github():
    text = "aws is AKIAABCDEFGHIJKLMNOP and gh is ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    out = redact_segment(text, segment_index=0, modes=["secrets"])
    types = {d.type for d in out.detections}
    assert "aws_access_key" in types
    assert "github_pat" in types
    assert "[REDACTED:AWS_ACCESS_KEY]" in out.redacted_text


def test_glossary_case_insensitive():
    g = Glossary(terms=[GlossaryTerm(term="Acme", severity="medium")])
    out = redact_segment(
        "ACME and acme and AcMe should all match",
        segment_index=0,
        modes=["glossary"],
        glossary=g,
    )
    assert out.redacted_text.count("[REDACTED:GLOSSARY:ACME]") == 3


def test_modes_are_disable_able():
    text = "email alex@example.com and akey AKIAABCDEFGHIJKLMNOP"
    out = redact_segment(text, segment_index=0, modes=["pii"])
    types = {d.type for d in out.detections}
    assert "email" in types
    assert "aws_access_key" not in types


def test_no_modes_no_redactions():
    out = redact_segment("alex@example.com", segment_index=0, modes=[])
    assert out.redacted_text == "alex@example.com"
    assert out.detections == []
