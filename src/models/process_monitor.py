from uuid import uuid4
from src import db

class ProcessMonitor(db.Model):
    __tablename__ = 'org_process_monitors'
    organization_id = db.Column(db.String(36), db.ForeignKey('portal_organizations.id'), nullable=True, index=True)
    __table_args__ = (db.UniqueConstraint('organization_id', 'process_number'),)
    id = db.Column(db.String(36),primary_key=True,default=lambda:str(uuid4()))
    process_number = db.Column(db.String(20),nullable=False)
    enabled = db.Column(db.Boolean,nullable=False,default=True)
    next_check = db.Column(db.String(40),nullable=False,index=True)
    last_lookup_id = db.Column(db.String(36))
