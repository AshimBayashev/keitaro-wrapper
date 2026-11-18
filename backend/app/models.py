from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CampaignRecord(Base):
    __tablename__ = "campaign_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    geo: Mapped[str] = mapped_column(String(2))
    initial_offer_id: Mapped[int] = mapped_column(Integer)
    domain_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int] = mapped_column(Integer)
    traffic_source_id: Mapped[int] = mapped_column(Integer)
    google_stream_id: Mapped[int] = mapped_column(Integer)
    offer_stream_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
