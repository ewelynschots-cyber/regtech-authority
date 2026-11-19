"""REG-FIN-001: protótipo isolado de conciliação de partidas dobradas."""
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from io import StringIO

FIELDS = ("entry_id", "date", "account", "debit", "credit", "counterparty", "document_id")

def audit_csv(content: str) -> dict:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or any(f not in reader.fieldnames for f in FIELDS):
        raise ValueError("CSV sem campos obrigatórios")
    totals = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    findings = []
    count = 0
    for lineno, row in enumerate(reader, start=2):
        if None in row or any(row.get(f) is None for f in FIELDS):
            raise ValueError(f"Linha {lineno}: estrutura CSV inválida")
        entry_id = row["entry_id"].strip()
        if not entry_id or not row["account"].strip():
            raise ValueError(f"Linha {lineno}: lançamento ou conta ausente")
        try:
            debit = Decimal(row["debit"].strip() or "0")
            credit = Decimal(row["credit"].strip() or "0")
        except InvalidOperation as exc:
            raise ValueError(f"Linha {lineno}: valor inválido") from exc
        if not debit.is_finite() or not credit.is_finite() or min(debit, credit) < 0:
            raise ValueError(f"Linha {lineno}: valor não finito ou negativo")
        if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
            raise ValueError(f"Linha {lineno}: informe apenas débito ou crédito positivo")
        totals[entry_id][0] += debit
        totals[entry_id][1] += credit
        count += 1
    for entry_id, (debit, credit) in sorted(totals.items()):
        if debit != credit:
            findings.append({"type": "UNBALANCED_ENTRY", "entry_id": entry_id,
                             "debit": str(debit), "credit": str(credit),
                             "difference": str(debit - credit)})
    return {"status": "review_required" if findings else "balanced_in_scope",
            "entries": len(totals), "rows": count, "findings": findings}
