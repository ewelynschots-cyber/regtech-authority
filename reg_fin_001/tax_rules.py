"""Catálogo experimental de regras normativas com vigência; não calcula tributos."""
from datetime import date
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TaxRule:
    rule_id: str
    effective_from: date
    effective_until: Optional[date]
    source_url: str
    reviewed_on: date
    validated: bool = False

    def applies_on(self, when: date) -> bool:
        return (self.effective_from <= when
                and (self.effective_until is None or when <= self.effective_until))

    def can_enforce(self, when: date) -> bool:
        return self.validated and self.applies_on(when)

def applicable_rules(rules: list[TaxRule], when: date) -> list[TaxRule]:
    return [rule for rule in rules if rule.can_enforce(when)]
