"""Inteligência patrimonial: análise de vínculos declarados, sem acesso ao SNIPER."""
from datetime import datetime, timezone
import re

KINDS = {"person", "company", "asset", "process", "credit"}
RELATIONS = {"partner", "administrator", "beneficial_owner", "owns", "linked_to", "creditor", "debtor", "party"}
PURPOSES = {"due_diligence", "kyc_kyb", "asset_recovery", "judicial_enforcement", "credit_analysis"}

def analyze_network(payload):
    if not isinstance(payload, dict) or set(payload) - {"name", "purpose", "legal_basis", "case_reference", "nodes", "edges", "sources"}:
        raise ValueError("Informe objeto válido e campos permitidos")
    name, purpose, basis = payload.get("name"), payload.get("purpose"), payload.get("legal_basis")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise ValueError("Nome da investigação obrigatório")
    if purpose not in PURPOSES or not isinstance(basis, str) or not 5 <= len(basis.strip()) <= 500:
        raise ValueError("Finalidade e fundamento jurídico documentados são obrigatórios")
    nodes, edges, sources = payload.get("nodes"), payload.get("edges"), payload.get("sources")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(sources, list):
        raise ValueError("Informe nodes, edges e sources como listas")
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
        clean_sources.append(source)
    source_ids = [s["id"] for s in clean_sources]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("IDs de fonte duplicados")
    ids, normalized_nodes = set(), []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "kind", "label", "source_ids"}:
            raise ValueError("Nó inválido")
        identifier, label, kind, refs = node.values() if False else (node["id"], node["label"], node["kind"], node["source_ids"])
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier in ids:
            raise ValueError("Identificador de nó inválido ou duplicado")
        if kind not in KINDS or not isinstance(label, str) or not 1 <= len(label.strip()) <= 200:
            raise ValueError("Tipo ou identificação inválidos")
        if not isinstance(refs, list) or not refs or any(ref not in source_ids for ref in refs):
            raise ValueError("Cada nó precisa de fonte identificada")
        ids.add(identifier)
        normalized_nodes.append(node)
    normalized_edges = []
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "relation", "source_ids"}:
            raise ValueError("Vínculo inválido")
        if edge["from"] not in ids or edge["to"] not in ids or edge["relation"] not in RELATIONS:
            raise ValueError("Vínculo referencia nó ou relação inexistente")
        if not isinstance(edge["source_ids"], list) or not edge["source_ids"] or any(ref not in source_ids for ref in edge["source_ids"]):
            raise ValueError("Cada vínculo precisa de fonte identificada")
        normalized_edges.append(edge)
    case_ref = payload.get("case_reference", "")
    if not isinstance(case_ref, str) or len(case_ref) > 160:
        raise ValueError("Referência do caso inválida")
    return {"name": name.strip(), "purpose": purpose, "legal_basis": basis.strip(),
            "case_reference": case_ref, "checked_at": datetime.now(timezone.utc).isoformat(),
            "nodes": normalized_nodes, "edges": normalized_edges, "sources": clean_sources,
            "summary": {"node_count": len(nodes), "edge_count": len(edges), "source_count": len(sources)},
            "alerts": [], "limitations": [
                "Dados declarados pelo usuário; não constituem consulta automática a cadastros oficiais.",
                "Sem acesso ao SNIPER/CNJ, bloqueios judiciais ou bases sigilosas.",
                "Vínculos não comprovam fraude, propriedade efetiva ou disponibilidade de bens."
            ]}
