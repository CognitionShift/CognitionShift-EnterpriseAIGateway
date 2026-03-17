"""Tests for outbound safety scanning."""

from app.services.outbound_safety import scan_outbound


def test_clean_output():
    result = scan_outbound("Here's a helpful answer about Python programming.")
    assert result.clean
    assert result.modified_content is None


def test_pii_in_output():
    result = scan_outbound("The user's SSN is 123-45-6789 which was in the database.")
    assert "output_pii_detected" in result.flags or "output_dlp_redacted" in result.flags


def test_api_key_in_output_redacted():
    result = scan_outbound("Found credential: sk-abc123def456ghi789jkl012345")
    assert result.modified_content is not None
    assert "[API KEY REDACTED]" in result.modified_content


def test_private_key_in_output_blocked():
    result = scan_outbound("Here's the key: -----BEGIN RSA PRIVATE KEY-----\nMIIEpA...")
    assert not result.clean
    assert "output_dlp_blocked" in result.flags
