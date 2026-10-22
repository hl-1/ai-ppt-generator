import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base

if TYPE_CHECKING:
    from app.modules.projects.models import Project


class ProjectOutline(Base):
    __tablename__ = "project_outlines"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_outlines_project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="generating")
    pages: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    blueprint: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_id: Mapped[str | None] = mapped_column(String(100))
    execution: Mapped[dict | None] = mapped_column(JSONB)
    input_signature: Mapped[str | None] = mapped_column(String(64))
    travel_research_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="outline")
