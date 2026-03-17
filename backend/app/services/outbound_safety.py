"""Outbound safety scanning — checks model responses before delivery to user."""

from dataclasses import dataclass, field
from app.services.content_safety import detect_pii
from app.services.dlp import DLPEngine, default_engine
import structlog

logger = structlog.get_logger()


@dataclass
class OutboundScanResult:
    clean: bool = True
    modified_content: str | None = None
    flags: list[str] = field(default_factory=list)
    pii_found: dict | None = None
    dlp_matches: list[dict] = field(default_factory=list)


def scan_outbound(content: str, dlp_engine: DLPEngine | None = None) -> OutboundScanResult:
    """
    Scan model output for PII leakage and DLP violations.
    Returns potentially modified content.
    """
    engine = dlp_engine or default_engine
    result = OutboundScanResult()

    # 1. PII detection on output
    pii = detect_pii(content)
    if pii:
        result.flags.append("output_pii_detected")
        result.pii_found = {k: len(v) for k, v in pii.items()}
        logger.info("outbound_pii_detected", pii_types=list(pii.keys()))

    # 2. DLP scan on output
    dlp_result = engine.scan(content)
    if dlp_result.blocked:
        result.clean = False
        result.modified_content = "[Response blocked by content policy]"
        result.flags.append("output_dlp_blocked")
        logger.warning("outbound_dlp_blocked", reason=dlp_result.block_reason)
        return result

    if dlp_result.modified:
        result.modified_content = dlp_result.clean_text
        result.flags.append("output_dlp_redacted")
        result.dlp_matches = dlp_result.matches

    return result
