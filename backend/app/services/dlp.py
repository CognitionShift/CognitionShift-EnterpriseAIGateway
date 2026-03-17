"""Data Loss Prevention (DLP) engine — configurable pattern matching and keyword filtering."""

import re
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


@dataclass
class DLPRule:
    name: str
    rule_type: str  # "regex", "keyword", "pattern"
    pattern: str
    action: str = "redact"  # "block", "redact", "warn", "allow"
    replacement: str = "[REDACTED]"
    enabled: bool = True


@dataclass
class DLPResult:
    modified: bool = False
    original_text: str = ""
    clean_text: str = ""
    matches: list[dict] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None


# Default DLP rules
DEFAULT_RULES: list[DLPRule] = [
    DLPRule(name="ssn", rule_type="regex", pattern=r"\b\d{3}-\d{2}-\d{4}\b", action="redact", replacement="[SSN REDACTED]"),
    DLPRule(name="credit_card", rule_type="regex", pattern=r"\b(?:\d{4}[-\s]?){3}\d{4}\b", action="redact", replacement="[CC REDACTED]"),
    DLPRule(name="us_phone", rule_type="regex", pattern=r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", action="warn"),
    DLPRule(name="aws_key", rule_type="regex", pattern=r"(?:AKIA|ASIA)[A-Z0-9]{16}", action="redact", replacement="[AWS KEY REDACTED]"),
    DLPRule(name="private_key", rule_type="regex", pattern=r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", action="block"),
    DLPRule(name="api_key_generic", rule_type="regex", pattern=r"(?:sk-|api[_-]?key)[a-zA-Z0-9_-]{20,}", action="redact", replacement="[API KEY REDACTED]"),
    DLPRule(name="password_field", rule_type="regex", pattern=r"(?:password|passwd|pwd)\s*[:=]\s*\S+", action="redact", replacement="[PASSWORD REDACTED]"),
]


class DLPEngine:
    """Configurable DLP engine with regex, keyword, and pattern rules."""

    def __init__(self, rules: list[DLPRule] | None = None):
        self.rules = rules or DEFAULT_RULES
        self._compiled: dict[str, re.Pattern] = {}
        for rule in self.rules:
            if rule.enabled and rule.rule_type in ("regex", "pattern"):
                try:
                    self._compiled[rule.name] = re.compile(rule.pattern, re.IGNORECASE)
                except re.error:
                    logger.warning("dlp_invalid_regex", rule=rule.name, pattern=rule.pattern)

    def scan(self, text: str) -> DLPResult:
        """Scan text and apply DLP rules. Returns potentially modified text."""
        result = DLPResult(original_text=text, clean_text=text)

        for rule in self.rules:
            if not rule.enabled:
                continue

            matches = []
            if rule.rule_type in ("regex", "pattern"):
                compiled = self._compiled.get(rule.name)
                if compiled:
                    matches = list(compiled.finditer(result.clean_text))
            elif rule.rule_type == "keyword":
                # Case-insensitive keyword search
                keywords = [k.strip() for k in rule.pattern.split(",")]
                for kw in keywords:
                    start = 0
                    lower_text = result.clean_text.lower()
                    lower_kw = kw.lower()
                    while True:
                        idx = lower_text.find(lower_kw, start)
                        if idx == -1:
                            break
                        matches.append(type("Match", (), {"group": lambda s=result.clean_text[idx:idx+len(kw)]: s, "start": lambda i=idx: i, "end": lambda i=idx+len(kw): i})())
                        start = idx + 1

            if not matches:
                continue

            for match in matches:
                result.matches.append({
                    "rule": rule.name,
                    "action": rule.action,
                    "match": match.group() if hasattr(match, "group") else str(match),
                })

            if rule.action == "block":
                result.blocked = True
                result.block_reason = f"DLP rule '{rule.name}' triggered — content blocked"
                logger.warning("dlp_blocked", rule=rule.name)
                return result
            elif rule.action == "redact":
                compiled = self._compiled.get(rule.name)
                if compiled:
                    result.clean_text = compiled.sub(rule.replacement, result.clean_text)
                    result.modified = True

        return result

    def add_rule(self, rule: DLPRule) -> None:
        """Add a custom DLP rule at runtime."""
        self.rules.append(rule)
        if rule.enabled and rule.rule_type in ("regex", "pattern"):
            try:
                self._compiled[rule.name] = re.compile(rule.pattern, re.IGNORECASE)
            except re.error:
                logger.warning("dlp_invalid_regex", rule=rule.name)

    @classmethod
    def from_config(cls, config: list[dict]) -> "DLPEngine":
        """Create DLP engine from configuration dict list."""
        rules = []
        for c in config:
            rules.append(DLPRule(
                name=c.get("name", "custom"),
                rule_type=c.get("type", "regex"),
                pattern=c.get("pattern", ""),
                action=c.get("action", "warn"),
                replacement=c.get("replacement", "[REDACTED]"),
                enabled=c.get("enabled", True),
            ))
        return cls(rules=DEFAULT_RULES + rules)


# Global default engine
default_engine = DLPEngine()
