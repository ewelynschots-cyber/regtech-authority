"""Run with flask --app wsgi recheck-processes; schedule externally."""
import os
from datetime import datetime,timezone,timedelta
from flask import current_app
from src import db
from src.integrations.datajud import lookup_process
from src.models.process_monitor import ProcessMonitor
from src.models.source_lookup import SourceLookup
from src.services.financial_analysis import canonical_hash


def run_due(limit=5):
    now = datetime.now(timezone.utc)
    ids = [r.id for r in ProcessMonitor.query.filter(ProcessMonitor.enabled.is_(True),ProcessMonitor.organization_id.is_not(None),ProcessMonitor.next_check<=now.isoformat()).order_by(ProcessMonitor.next_check).limit(limit)]
    count = 0
    for identifier in ids:
        # Conditional claim avoids duplicate work across concurrent runners.
        claimed = ProcessMonitor.query.filter_by(id=identifier,enabled=True).filter(ProcessMonitor.next_check<=now.isoformat()).update({'next_check':(now+timedelta(minutes=15)).isoformat()})
        db.session.commit()
        if not claimed:
            continue
        row = db.session.get(ProcessMonitor,identifier)
        payload = lookup_process(row.process_number,current_app.config.get('DATAJUD_API_KEY') or os.getenv('DATAJUD_API_KEY'))
        snapshot = SourceLookup(organization_id=row.organization_id, provider='datajud',process_number=row.process_number,checked_at=payload['checked_at'],status=payload['status'],payload=payload,payload_sha256=canonical_hash(payload))
        db.session.add(snapshot)
        db.session.flush()
        row.last_lookup_id = snapshot.id
        row.next_check = (datetime.now(timezone.utc)+timedelta(hours=24 if payload['status'] in ('found','not_found') else 1)).isoformat()
        db.session.commit()
        count += 1
    return count
