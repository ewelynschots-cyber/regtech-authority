"""Inteligência patrimonial: análise de vínculos declarados, sem acesso ao SNIPER."""
from datetime import datetime, timezone
import re

from src.services.financial_analysis import flag, iso_date, list_rows

KINDS = {"person", "company", "asset", "process", "credit"}
RELATIONS = {"partner", "administrator", "beneficial_owner", "owns", "linked_to", "creditor", "debtor", "party"}
PURPOSES = {"due_diligence", "kyc_kyb", "asset_recovery", "judicial_enforcement", "credit_analysis", "fiscal_diligence"}

def analyze_network(payload):
    if not isinstance(payload, dict) or set(payload) - {"name", "purpose", "legal_basis", "case_reference", "nodes", "edges", "sources", "events"}:
        raise ValueError("Informe objeto válido e campos permitidos")
    name, purpose, basis = payload.get("name"), payload.get("purpose"), payload.get("legal_basis")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise ValueError("Nome da investigação obrigatório")
    if not isinstance(purpose, str) or purpose not in PURPOSES or not isinstance(basis, str) or not 5 <= len(basis.strip()) <= 500:
        raise ValueError("Finalidade e fundamento jurídico documentados são obrigatórios")
    nodes, edges, sources = payload.get("nodes"), payload.get("edges"), payload.get("sources")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(sources, list):
        raise ValueError("Informe nodes, edges e sources como listas")
    if not nodes or not sources:
        raise ValueError("Informe ao menos uma entidade e uma fonte")
    if len(nodes) > 250 or len(edges) > 1000 or len(sources) > 100:
        raise ValueError("Limite de registros excedido")
    clean_sources = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"id", "reference", "accessed_at"}:
            raise ValueError("Fonte deve conter id, reference e accessed_at")
        if any(not isinstance(source[k], str) or not source[k].strip() or len(source[k]) > 500 for k in source):
            raise ValueError("Fonte inválida")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source["id"]):
            raise ValueError("ID da fonte inválido")
        try:
            accessed_at = datetime.fromisoformat(source["accessed_at"])
            if accessed_at.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ValueError("Data de consulta deve conter horário e fuso ISO 8601") from None
        clean_sources.append({**source, "status": "declared"})
    source_ids = [s["id"] for s in clean_sources]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("IDs de fonte duplicados")
    ids, normalized_nodes = set(), []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "kind", "label", "source_ids"}:
            raise ValueError("Nó inválido")
        identifier, label, kind, refs = (node["id"], node["label"], node["kind"], node["source_ids"])
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier in ids:
            raise ValueError("Identificador de nó inválido ou duplicado")
        if not isinstance(kind, str) or kind not in KINDS or not isinstance(label, str) or not 1 <= len(label.strip()) <= 200:
            raise ValueError("Tipo ou identificação inválidos")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in source_ids for ref in refs):
            raise ValueError("Cada nó precisa de fonte identificada")
        ids.add(identifier)
        normalized_nodes.append(node)
    normalized_edges = []
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "relation", "source_ids"}:
            raise ValueError("Vínculo inválido")
        if any(not isinstance(edge[key], str) for key in ("from", "to", "relation")) or (
            edge["from"] not in ids or edge["to"] not in ids or edge["relation"] not in RELATIONS
        ):
            raise ValueError("Vínculo referencia nó ou relação inexistente")
        if not isinstance(edge["source_ids"], list) or not edge["source_ids"] or any(not isinstance(ref, str) or ref not in source_ids for ref in edge["source_ids"]):
            raise ValueError("Cada vínculo precisa de fonte identificada")
        normalized_edges.append(edge)
    case_ref = payload.get("case_reference", "")
    if not isinstance(case_ref, str) or len(case_ref) > 160:
        raise ValueError("Referência do caso inválida")
    events = chronology(payload.get("events", []), ids, source_ids)
    alerts = []
    assessments = {}
    for event in events:
        entity = event["entity_id"]
        if event["kind"] == "tax_assessment":
            assessments[entity] = event
        elif event["kind"] == "asset_transfer" and entity in assessments:
            assessment = assessments[entity]
            if assessment["date"] < event["date"]:
                flag(alerts, "transfer_after_assessment",
                     "Conferir a titularidade, a contraprestação e os documentos da transferência posterior à autuação.",
                     evidence={"assessment": assessment, "transfer": event})
    return {"module": "assets", "name": name.strip(), "purpose": purpose, "legal_basis": basis.strip(),
            "case_reference": case_ref, "checked_at": datetime.now(timezone.utc).isoformat(),
            "nodes": normalized_nodes, "edges": normalized_edges, "sources": clean_sources,
            "summary": {"node_count": len(nodes), "edge_count": len(edges), "source_count": len(sources), "alert_count": len(alerts)},
            "events": events, "alerts": alerts, "reference_sources": [],
            "method": "Comparação cronológica de eventos declarados para a mesma entidade.", "limitations": [
                "Fontes declaradas pelo usuário, sem verificação independente de seu conteúdo.",
                "Sem acesso ao SNIPER/CNJ, bloqueios judiciais ou bases sigilosas.",
                "Vínculos não comprovam fraude, propriedade efetiva ou disponibilidade de bens."
            ]}


def chronology(raw_events, entity_ids, source_ids):
    events = []
    fields = {"date", "kind", "entity_id", "description", "source_ids"}
    for event in list_rows(raw_events, "Cronologia", maximum=500, allow_empty=True):
        if not isinstance(event, dict) or set(event) != fields:
            raise ValueError("Evento deve informar data, tipo, entidade, descrição e fontes")
        entity, kind, description, refs = (
            event["entity_id"], event["kind"], event["description"], event["source_ids"]
        )
        if not isinstance(entity, str) or entity not in entity_ids:
            raise ValueError("Evento referencia entidade inexistente")
        if kind not in ("tax_assessment", "asset_transfer", "corporate_change", "other"):
            raise ValueError("Tipo de evento inválido")
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 500:
            raise ValueError("Descrição de evento inválida")
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, str) or ref not in source_ids for ref in refs
        ):
            raise ValueError("Cada evento precisa de fonte identificada")
        events.append({**event, "date": iso_date(event["date"], "Data do evento"),
                       "description": description.strip()})
    return sorted(events, key=lambda event: (event["date"], event["kind"] == "tax_assessment"))
