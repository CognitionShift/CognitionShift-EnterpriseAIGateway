"""Content safety service — PII detection and prompt injection detection."""

import re
import structlog
from dataclasses import dataclass, field

logger = structlog.get_logger()


@dataclass
class SafetyResult:
    safe: bool = True
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    action: str = "allow"  # allow, warn, block


# PII patterns
PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

# Prompt injection indicators
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:DAN|evil|unrestricted)", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:your\s+)?(?:previous\s+)?(?:instructions|rules|guidelines)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*(?:is|:)", re.IGNORECASE),
    re.compile(r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a|an)\s+(?:different|new|evil)", re.IGNORECASE),
    re.compile(r"override\s+(?:your\s+)?(?:safety|content)\s+(?:filters|policies|restrictions)", re.IGNORECASE),
    re.compile(r"\[SYSTEM\]|\[INST\]|<\|system\|>|<\|im_start\|>", re.IGNORECASE),
]


def detect_pii(text: str) -> dict[str, list[str]]:
    """Detect PII patterns in text. Returns dict of type -> list of matches."""
    found: dict[str, list[str]] = {}
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            found[pii_type] = matches
    return found


def detect_injection(text: str) -> list[str]:
    """Detect prompt injection attempts. Returns list of matched pattern names."""
    flags = []
    for i, pattern in enumerate(INJECTION_PATTERNS):
        if pattern.search(text):
            flags.append(f"injection_pattern_{i}")
    return flags


def check_content_safety(text: str, policy: dict | None = None) -> SafetyResult:
    """
    Run content safety checks on input text.
    
    Policy dict can control behavior:
      - pii_action: "block" | "warn" | "allow" (default: "warn")
      - injection_action: "block" | "warn" | "allow" (default: "block")
    """
    policy = policy or {}
    pii_action = policy.get("pii_action", "warn")
    injection_action = policy.get("injection_action", "block")

    result = SafetyResult()

    # PII check
    pii = detect_pii(text)
    if pii:
        result.flags.append("pii_detected")
        result.details["pii"] = {k: len(v) for k, v in pii.items()}
        if pii_action == "block":
            result.safe = False
            result.action = "block"
            logger.warning("content_safety_pii_blocked", pii_types=list(pii.keys()))
        elif pii_action == "warn":
            logger.info("content_safety_pii_warning", pii_types=list(pii.keys()))

    # Injection check
    injection_flags = detect_injection(text)
    if injection_flags:
        result.flags.append("injection_detected")
        result.details["injection"] = injection_flags
        if injection_action == "block":
            result.safe = False
            result.action = "block"
            logger.warning("content_safety_injection_blocked", patterns=injection_flags)
        elif injection_action == "warn":
            logger.info("content_safety_injection_warning", patterns=injection_flags)

    return result
