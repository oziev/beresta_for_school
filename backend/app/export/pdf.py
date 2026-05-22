"""WeasyPrint-based PDF export for materials and dashboard."""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dashboard.aggregator import aggregate
from app.models import Kit, Material
from app.schemas import KitExportRequest, Task

log = logging.getLogger(__name__)

PDFMode = Literal["worksheet", "dashboard"]

# Jinja2 environment setup
from jinja2 import Environment, FileSystemLoader, select_autoescape

_jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_html(template_name: str, context: dict) -> str:
    """Render HTML template with given context."""
    tmpl = _jinja_env.get_template(template_name)
    return tmpl.render(**context)


def get_pdf_template(template_name: str) -> str:
    """Map template name to actual HTML template file."""
    templates = {
        "classic": "pdf/worksheet_classic.html",
        "two-columns": "pdf/worksheet_two_columns.html",
        "infographic": "pdf/worksheet_infographic.html",
        "cheatsheet": "pdf/worksheet_cheatsheet.html",
    }
    return templates.get(template_name, "pdf/worksheet_classic.html")


async def render_pdf(
    material_id: uuid.UUID,
    mode: PDFMode,
    db: AsyncSession,
    template_name: str = "classic",
) -> bytes:
    """
    Render PDF from material data.
    
    Args:
        material_id: UUID of the material
        mode: "worksheet" or "dashboard"
        db: AsyncSession for database queries
        template_name: Template style (classic, two-columns, infographic, cheatsheet)
    
    Returns:
        PDF as bytes
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("weasyprint not installed. Run: pip install weasyprint") from exc

    if mode == "worksheet":
        # Fetch material from database
        res = await db.execute(select(Material).where(Material.id == material_id))
        material = res.scalar_one_or_none()
        
        if not material:
            raise ValueError(f"Material not found: {material_id}")
        
        # Parse tasks from stored JSON
        tasks = [Task.model_validate(t) for t in material.tasks]
        
        # Select template based on user choice
        template_file = get_pdf_template(template_name)
        
        # Render HTML
        html = _render_html(
            template_file,
            {
                "material": material,
                "tasks": tasks,
                "template_name": template_name,
            }
        )

    else:  # mode == "dashboard"
        # Aggregate statistics for dashboard
        stats = await aggregate(material_id, db)
        
        if not stats:
            raise ValueError(f"No data found for material: {material_id}")
        
        # Render dashboard HTML
        html = _render_html(
            "pdf/dashboard.html",
            {
                "stats": stats,
                "material_id": material_id,
            }
        )

    # Generate PDF
    return HTML(string=html, base_url=".").write_pdf()


async def render_worksheet_pdf(
    material_id: uuid.UUID,
    db: AsyncSession,
    template_name: str = "classic",
) -> bytes:
    """Convenience function for worksheet PDF export."""
    return await render_pdf(material_id, "worksheet", db, template_name)


async def render_dashboard_pdf(
    material_id: uuid.UUID,
    db: AsyncSession,
) -> bytes:
    """Convenience function for dashboard PDF export."""
    return await render_pdf(material_id, "dashboard", db)


async def render_kit_pdf(
    kit_id: uuid.UUID,
    db: AsyncSession,
    export: KitExportRequest,
) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("weasyprint not installed. Run: pip install weasyprint") from exc

    res = await db.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == kit_id))
    kit = res.scalar_one_or_none()
    if kit is None:
        raise ValueError(f"Kit not found: {kit_id}")

    html = _render_html(
        "pdf/kit.html",
        {
            "kit": kit,
            "items": list(kit.items),
            "export": export,
            "design": export.design,
        },
    )
    return HTML(string=html, base_url=".").write_pdf()