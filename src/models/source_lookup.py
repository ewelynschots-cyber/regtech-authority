from uuid import uuid4
from src import db


class SourceLookup(db.Model):
    __tablename__='source_lookups'
    id=db.Column(db.String(36),primary_key=True,default=lambda:str(uuid4()))
    provider=db.Column(db.String(30),nullable=False)
    process_number=db.Column(db.String(20),nullable=False,index=True)
    checked_at=db.Column(db.String(40),nullable=False,index=True)
    status=db.Column(db.String(30),nullable=False)
    payload=db.Column(db.JSON,nullable=False)
    payload_sha256=db.Column(db.String(64),nullable=False)
