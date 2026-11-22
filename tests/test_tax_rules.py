import unittest
from datetime import date
from reg_fin_001.tax_rules import TaxRule, applicable_rules

class TaxRulesTests(unittest.TestCase):
    def test_unvalidated_rule_never_enforced(self):
        rule = TaxRule("TEST", date(2026, 1, 1), None, "https://example.org", date(2026, 11, 22))
        self.assertFalse(rule.can_enforce(date(2026, 11, 22)))

    def test_effective_window(self):
        rule = TaxRule("TEST", date(2026, 1, 1), date(2026, 12, 31), "https://example.org", date(2026, 11, 22), True)
        self.assertFalse(rule.can_enforce(date(2025, 12, 31)))
        self.assertTrue(rule.can_enforce(date(2026, 6, 1)))
        self.assertFalse(rule.can_enforce(date(2027, 1, 1)))

    def test_only_validated_applicable_rules(self):
        a = TaxRule("A", date(2026, 1, 1), None, "https://example.org", date(2026, 11, 22), True)
        b = TaxRule("B", date(2026, 1, 1), None, "https://example.org", date(2026, 11, 22), False)
        self.assertEqual([r.rule_id for r in applicable_rules([a, b], date(2026, 11, 22))], ["A"])

if __name__ == "__main__":
    unittest.main()
