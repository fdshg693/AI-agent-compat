"""Compatibility exports for the scoped-rules common model."""

from agent_tooling.hooks.common.rules import (
    MatchedRule,
    Rule,
    RuleOrigin,
    RuleValidationError,
    parse_rule,
)

__all__ = ["MatchedRule", "Rule", "RuleOrigin", "RuleValidationError", "parse_rule"]
