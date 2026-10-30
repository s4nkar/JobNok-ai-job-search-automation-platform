import uuid

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, UUIDPKMixin, CreatedAtMixin


class Template(Base, UUIDPKMixin, CreatedAtMixin):
    __tablename__ = "templates"
    __table_args__ = (
        Index("templates_user_id_idx", "user_id"),
        Index("templates_category_idx", "category"),
        # Defense in depth alongside the Pydantic max_length/Literal
        # boundary checks in schemas.py - belt-and-suspenders per this
        # codebase's input length convention, in case a future code path
        # ever writes this table without going through TemplateIn/Update.
        CheckConstraint("char_length(name) <= 100", name="templates_name_length_check"),
        CheckConstraint("char_length(content) <= 5000", name="templates_content_length_check"),
        CheckConstraint(
            "category in ('Cold DM - Recruiter', 'Cold DM - Hiring Manager', 'Follow-Up', 'Referral Ask', 'Email Outreach', 'Custom')",
            name="templates_category_check",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, server_default="Custom", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    placeholders: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", nullable=False
    )
    use_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
