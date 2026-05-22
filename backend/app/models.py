"""SQLAlchemy models — seven tables from the product specification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    demo_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    materials: Mapped[list[Material]] = relationship(back_populates="user")
    templates: Mapped[list[UserTemplate]] = relationship(back_populates="user")
    edits: Mapped[list[TeacherEdit]] = relationship(back_populates="user")
    lesson_plans: Mapped[list[LessonPlan]] = relationship(back_populates="user")
    kits: Mapped[list[Kit]] = relationship(back_populates="user")
    design_settings: Mapped[DesignSettings | None] = relationship(back_populates="user", uselist=False)
    sources: Mapped[list[TeacherSource]] = relationship(back_populates="user")
    profile: Mapped[TeacherProfile | None] = relationship(
        back_populates="user",
        uselist=False,
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_email: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("users.email", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(50), nullable=False)
    generation_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tasks: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    teacher_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    user: Mapped[User | None] = relationship(back_populates="materials")
    sessions: Mapped[list[StudentSession]] = relationship(back_populates="material")
    dashboard_logs: Mapped[list[DashboardLog]] = relationship(back_populates="material")


class StudentSession(Base):
    __tablename__ = "student_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=True, index=True)
    student_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initial_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answers: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    hint_used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    material: Mapped[Material | None] = relationship(back_populates="sessions")


class DashboardLog(Base):
    __tablename__ = "dashboard_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_index: Mapped[int] = mapped_column(Integer, nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_time_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    material: Mapped[Material] = relationship(back_populates="dashboard_logs")


class UserTemplate(Base):
    __tablename__ = "user_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_email: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.email", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="templates")


class TeacherEdit(Base):
    __tablename__ = "teacher_edits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_email: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.email", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    kit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kits.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    task_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="edits")


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"

    user_email: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.email", ondelete="CASCADE"),
        primary_key=True,
    )
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    total_edits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_trained: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    user: Mapped[User] = relationship(back_populates="profile")


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email: Mapped[str | None] = mapped_column(String(255), ForeignKey("users.email", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stages: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    lesson_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="lesson_plans")
    kits: Mapped[list[Kit]] = relationship(back_populates="lesson_plan")


class Kit(Base):
    __tablename__ = "kits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email: Mapped[str | None] = mapped_column(String(255), ForeignKey("users.email"), nullable=True, index=True)
    lesson_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lesson_plans.id"), nullable=True, index=True)
    parent_kit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("kits.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(50), nullable=False)
    lesson_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    kit_type: Mapped[str] = mapped_column(String(20), default="student", server_default="student")
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    template_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="kits")
    lesson_plan: Mapped[LessonPlan | None] = relationship(back_populates="kits")
    items: Mapped[list[KitItem]] = relationship(back_populates="kit", cascade="all, delete-orphan", order_by="KitItem.sort_order")


class KitItem(Base):
    __tablename__ = "kit_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_levels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    complexity_level: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    complexity_distribution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    teacher_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_key: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    example_mistakes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    kit: Mapped[Kit] = relationship(back_populates="items")


class DesignSettings(Base):
    __tablename__ = "design_settings"

    user_email: Mapped[str] = mapped_column(String(255), ForeignKey("users.email"), primary_key=True)
    font_family: Mapped[str] = mapped_column(String(50), default="Inter", server_default="Inter")
    font_size: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    margins: Mapped[str] = mapped_column(String(20), default="normal", server_default="normal")
    show_date: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    show_name: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    show_class: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user: Mapped[User] = relationship(back_populates="design_settings")


class TeacherSource(Base):
    __tablename__ = "teacher_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email: Mapped[str | None] = mapped_column(String(255), ForeignKey("users.email"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="sources")
