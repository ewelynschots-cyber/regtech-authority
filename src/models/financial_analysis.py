from datetime import datetime, timezone
from uuid import uuid4
from src import db


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class FinancialAnalysis(db.Model):
    __tablename__ = 'financial_analyses'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    module = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.String(40), nullable=False, default=now_iso)
    input_payload = db.Column(db.JSON, nullable=False)
    result_payload = db.Column(db.JSON, nullable=False)
    input_sha256 = db.Column(db.String(64), nullable=False)
    result_sha256 = db.Column(db.String(64), nullable=False)


class FinancialReview(db.Model):
    __tablename__ = 'financial_reviews'
    __table_args__ = (db.UniqueConstraint('analysis_id', 'revision'),)
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id = db.Column(db.String(36), db.ForeignKey('financial_analyses.id'), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    event = db.Column(db.JSON, nullable=False)
    event_sha256 = db.Column(db.String(64), nullable=False)
