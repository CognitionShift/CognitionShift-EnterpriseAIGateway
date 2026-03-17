"""Tests for DLP engine."""

from app.services.dlp import DLPEngine, DLPRule, default_engine


def test_detect_ssn():
    result = default_engine.scan("My SSN is 123-45-6789")
    assert result.modified
    assert "[SSN REDACTED]" in result.clean_text
    assert "123-45-6789" not in result.clean_text


def test_detect_credit_card():
    result = default_engine.scan("Card: 4111-1111-1111-1111")
    assert result.modified
    assert "[CC REDACTED]" in result.clean_text


def test_detect_aws_key():
    result = default_engine.scan("Key is AKIAIOSFODNN7EXAMPLE")
    assert result.modified
    assert "[AWS KEY REDACTED]" in result.clean_text


def test_block_private_key():
    result = default_engine.scan("Here's my key: -----BEGIN RSA PRIVATE KEY-----")
    assert result.blocked
    assert result.block_reason is not None


def test_detect_api_key():
    result = default_engine.scan("My key is sk-1234567890abcdefghij1234")
    assert result.modified
    assert "[API KEY REDACTED]" in result.clean_text


def test_detect_password():
    result = default_engine.scan("The password: SuperSecret123!")
    assert result.modified
    assert "[PASSWORD REDACTED]" in result.clean_text


def test_clean_text_unchanged():
    result = default_engine.scan("What's the weather like today?")
    assert not result.modified
    assert not result.blocked
    assert result.clean_text == "What's the weather like today?"


def test_custom_rule():
    engine = DLPEngine(rules=[
        DLPRule(name="custom_id", rule_type="regex", pattern=r"EMP-\d{6}", action="redact", replacement="[ID REDACTED]"),
    ])
    result = engine.scan("Employee EMP-123456 needs access")
    assert result.modified
    assert "[ID REDACTED]" in result.clean_text


def test_keyword_rule():
    engine = DLPEngine(rules=[
        DLPRule(name="confidential", rule_type="keyword", pattern="confidential,top secret", action="warn"),
    ])
    result = engine.scan("This is a confidential document")
    assert len(result.matches) > 0
    assert result.matches[0]["rule"] == "confidential"


def test_from_config():
    config = [
        {"name": "test_rule", "type": "regex", "pattern": r"TEST-\d+", "action": "redact", "replacement": "[REDACTED]"},
    ]
    engine = DLPEngine.from_config(config)
    result = engine.scan("Case TEST-42 and also SSN 123-45-6789")
    assert "[REDACTED]" in result.clean_text
    assert "[SSN REDACTED]" in result.clean_text
