"""Pydantic schemas for API validation (aligned with FR‑03 and JSON task shape)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from typing import Literal

PDFMode = Literal["worksheet", "dashboard"]

# --- Generation & tasks ---

TaskType = Literal["test", "open", "problem", "creative", "graph"]
DifficultyDistribution = Literal["uniform", "more_basic", "more_advanced"]
AnswerFormat = Literal["test", "open_text", "mixed"]
HandoutType = Literal["cards", "worksheet", "memo", "reflection", "table", "schema", "homework"]
ActivityType = Literal["quiz", "explanation", "practice", "reflection", "homework"]
LessonType = Literal["discovery", "reflection", "control", "combined"]
LayoutMode = Literal["cards_grid", "two_cards", "flipchart", "full_page", "combined"]
PaperSize = Literal["A4", "A3"]
Orientation = Literal["portrait", "landscape"]
SourceMode = Literal["auto", "my"]
ScaffoldingStyle = Literal["questions", "steps", "both"]
EmotionalReflectionType = Literal["classic", "emotional", "both"]


class SourceConfig(BaseModel):
    enabled: bool = False
    mode: SourceMode = "auto"
    my_sources: list[dict[str, str]] = Field(default_factory=list)
    show_in_pdf: bool = False


class HotMistakes(BaseModel):
    enabled: bool = False
    count: int = Field(default=5, ge=3, le=10)
    add_lifehacks: bool = False
    add_common_traps: bool = False


class TimingConfig(BaseModel):
    enabled: bool = False
    lesson_duration: int = Field(default=40, ge=30, le=90)
    show_on_handout: bool = False
    add_extra_tasks: bool = False


class ScaffoldingConfig(BaseModel):
    enabled: bool = False
    min_level: int = Field(default=2, ge=1, le=3)
    style: ScaffoldingStyle = "steps"
    show_on_error_only: bool = False


class EmotionalReflection(BaseModel):
    enabled: bool = False
    type: EmotionalReflectionType = "both"
    add_creative: bool = False
    collect_stats: bool = False


class PedagogicalFeatures(BaseModel):
    sources: SourceConfig = Field(default_factory=SourceConfig)
    mistakes: HotMistakes = Field(default_factory=HotMistakes)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    scaffolding: ScaffoldingConfig = Field(default_factory=ScaffoldingConfig)
    emotional: EmotionalReflection = Field(default_factory=EmotionalReflection)


class GenerationParams(BaseModel):
    """Manual tuning before generation (FR‑03)."""

    task_count: int = Field(default=5, ge=3, le=10)
    task_types: list[TaskType] = Field(
        default_factory=lambda: ["test", "problem"],
        description="Подмножество типов из ТЗ: test, problem, creative, graph.",
    )
    difficulty_distribution: DifficultyDistribution = "uniform"
    diagnostic_time_sec: int = Field(default=30, ge=10, le=120)
    answer_format: AnswerFormat = "mixed"
    game_mode: bool = False
    game_theme: str | None = Field(
        default=None,
        description="Short theme label when game_mode is enabled (detective / quest).",
    )
    pedagogical: PedagogicalFeatures = Field(default_factory=PedagogicalFeatures)


class Task(BaseModel):
    """Single worksheet task as stored in `materials.tasks` JSONB."""

    text: str
    options: list[str] | None = None
    correct: int | str
    time_limit_sec: int = Field(default=30, ge=5, le=600)
    adaptive_level: int = Field(default=2, ge=1, le=3)
    type: TaskType = "test"

    @field_validator("options", mode="before")
    @classmethod
    def empty_options_to_none(cls, v: Any) -> Any:
        if v == []:
            return None
        return v


class MaterialBase(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    grade: int = Field(ge=1, le=11)
    subject: str = Field(min_length=1, max_length=50)
    generation_params: GenerationParams | None = None


class MaterialCreate(MaterialBase):
    tasks: list[Task] = Field(default_factory=list)


class MaterialRead(MaterialBase):
    id: uuid.UUID
    tasks: list[Task]
    created_at: datetime
    teacher_edited: bool

    model_config = {"from_attributes": True}


class MaterialUpdate(BaseModel):
    """Body for PUT /materials/{id} — full task list replacement."""

    tasks: list[Task]


class GenerateRequest(BaseModel):
    topic: str
    grade: int = Field(ge=1, le=11)
    subject: str
    generation_params: GenerationParams | None = None


class GenerateResponse(BaseModel):
    material_id: uuid.UUID
    tasks: list[Task]


class TeacherSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)


class TeacherSourceRead(TeacherSourceCreate):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class RegenerateTaskRequest(BaseModel):
    material_id: uuid.UUID
    task_index: int = Field(ge=0)
    feedback: str | None = None


class RegenerateTaskResponse(BaseModel):
    task: Task


# --- Adaptive ---


class DiagnosticQuestion(BaseModel):
    text: str
    options: list[str]
    correct: int
    time_sec: int


class DiagnosticPayload(BaseModel):
    diagnostic: list[DiagnosticQuestion]


class AdaptDiagnoseRequest(BaseModel):
    session_id: uuid.UUID
    answers: list[dict[str, Any]]


class AdaptAnswerRequest(BaseModel):
    session_id: uuid.UUID
    task_index: int
    answer: str | int
    time_spent: float


# --- Dashboard ---


class DashboardJsonResponse(BaseModel):
    stats: dict[str, Any]
    advice: str | None = None


# --- Templates & profile ---


class TemplateSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    params: GenerationParams


class TemplateListItem(BaseModel):
    id: uuid.UUID
    name: str


class TeacherProfilePayload(BaseModel):
    profile: dict[str, Any] | None
    total_edits: int


class LessonStage(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    goal: str | None = None
    default_duration: int | None = Field(default=None, ge=1, le=180)
    time_minutes: int | None = Field(default=None, ge=1, le=180)
    custom_duration: int | None = Field(default=None, ge=1, le=180)
    activity_type: ActivityType = "practice"
    needs_handout: bool = True
    recommended_handout_type: HandoutType = "worksheet"


class LessonPlanRead(BaseModel):
    id: uuid.UUID
    name: str | None
    original_filename: str | None
    content: str
    stages: list[LessonStage]
    lesson_type: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadLessonPlanResponse(BaseModel):
    lesson_plan_id: uuid.UUID | None = None
    content: str
    stages: list[LessonStage]


class ContentLevels(BaseModel):
    basic: str
    medium: str
    advanced: str


class KitItemBase(BaseModel):
    stage_name: str | None = Field(default=None, max_length=100)
    type: HandoutType = "worksheet"
    title: str = Field(min_length=1, max_length=200)
    content_levels: ContentLevels
    complexity_level: int = Field(default=2, ge=1, le=3)
    complexity_distribution: DifficultyDistribution = "uniform"
    sort_order: int = Field(default=0, ge=0)
    teacher_notes: str | None = None
    answer_key: dict[str, Any] | None = None
    example_mistakes: list[dict[str, Any]] | None = None


class KitItemRead(KitItemBase):
    id: uuid.UUID
    kit_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class KitItemReorderRequest(BaseModel):
    order: list[uuid.UUID] = Field(min_length=1)


class KitItemUpdate(BaseModel):
    stage_name: str | None = Field(default=None, max_length=100)
    type: HandoutType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_levels: ContentLevels | None = None
    complexity_level: int | None = Field(default=None, ge=1, le=3)
    complexity_distribution: DifficultyDistribution | None = None
    sort_order: int | None = Field(default=None, ge=0)
    teacher_notes: str | None = None
    answer_key: dict[str, Any] | None = None
    example_mistakes: list[dict[str, Any]] | None = None


class KitItemCreate(KitItemBase):
    pass


class GenerateFromPlanRequest(BaseModel):
    lesson_plan_id: uuid.UUID | None = None
    lesson_plan_content: str | None = None
    stages: list[LessonStage] | None = None
    topic: str | None = Field(default=None, max_length=255)
    grade: int = Field(ge=1, le=11)
    subject: str = Field(min_length=1, max_length=50)
    lesson_type: LessonType | None = None
    mode: str = "from_plan"
    global_complexity: int = Field(default=2, ge=1, le=3)
    pedagogical: PedagogicalFeatures = Field(default_factory=PedagogicalFeatures)
    save_plan: bool = False
    plan_name: str | None = Field(default=None, max_length=200)


class GenerateFromScratchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    grade: int = Field(ge=1, le=11)
    subject: str = Field(min_length=1, max_length=50)
    lesson_type: LessonType = "combined"
    global_complexity: int = Field(default=2, ge=1, le=3)
    pedagogical: PedagogicalFeatures = Field(default_factory=PedagogicalFeatures)


class DefaultPlanRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    grade: int = Field(ge=1, le=11)
    subject: str = Field(min_length=1, max_length=50)
    lesson_type: LessonType = "combined"


class KitRead(BaseModel):
    id: uuid.UUID
    lesson_plan_id: uuid.UUID | None
    parent_kit_id: uuid.UUID | None = None
    name: str | None = None
    topic: str | None
    grade: int
    subject: str
    lesson_type: str | None = None
    mode: str | None = None
    kit_type: str = "student"
    is_template: bool = False
    template_name: str | None = None
    version: int = 1
    feedback: dict[str, Any] | None = None
    created_at: datetime
    items: list[KitItemRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class GenerateFromPlanResponse(BaseModel):
    kit_id: uuid.UUID
    items: list[KitItemRead]


class KitTemplateRequest(BaseModel):
    template_name: str = Field(min_length=1, max_length=200)


class LessonFeedback(BaseModel):
    ratings: dict[str, int] = Field(default_factory=dict)
    comments: dict[str, str] = Field(default_factory=dict)
    general_comment: str | None = None


class ExampleMistakesPayload(BaseModel):
    example_mistakes: list[dict[str, Any]] = Field(default_factory=list)


class DesignSettingsPayload(BaseModel):
    font_family: Literal["Arial", "Times", "Inter", "Segoe UI"] = "Inter"
    font_size: int = Field(default=12, ge=10, le=16)
    margins: Literal["normal", "narrow", "wide"] = "normal"
    show_date: bool = True
    show_name: bool = True
    show_class: bool = True


class KitExportRequest(BaseModel):
    layout: LayoutMode = "full_page"
    paper_size: PaperSize = "A4"
    orientation: Orientation = "portrait"
    headers: bool = True
    version: Literal["student", "teacher"] = "student"
    title_page: bool = False
    page_numbers: bool = False
    design: DesignSettingsPayload | None = None
