import unittest
from reg_fin_001.audit import audit_csv

HEADER = "entry_id,date,account,debit,credit,counterparty,document_id\n"

class AuditTests(unittest.TestCase):
    def test_balanced(self):
        data = HEADER + "1,2026-11-19,Cash,100.10,0,A,D1\n1,2026-11-19,Revenue,0,100.10,A,D1\n"
        self.assertEqual(audit_csv(data)["status"], "balanced_in_scope")

    def test_unbalanced(self):
        data = HEADER + "1,2026-11-19,Cash,100,0,A,D1\n1,2026-11-19,Revenue,0,90,A,D1\n"
        self.assertEqual(audit_csv(data)["findings"][0]["difference"], "10")

    def test_invalid_amount(self):
        with self.assertRaises(ValueError):
            audit_csv(HEADER + "1,2026-11-19,Cash,NaN,0,A,D1\n")

    def test_missing_schema(self):
        with self.assertRaises(ValueError):
            audit_csv("id,value\n1,100\n")

if __name__ == "__main__":
    unittest.main()
