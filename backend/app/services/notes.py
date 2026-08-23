from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.enums import Confidence, NoteCategory, NoteInputType


def create_note(db: Session, values: dict[str, Any]) -> models.TrainingNote:
    confidence = values.get("classification_confidence") or Confidence.MODERATE
    item = models.TrainingNote(
        primary_category=NoteCategory(values["primary_category"]),
        title=values["title"],
        raw_input=values.get("raw_input") or values.get("cleaned_note") or "",
        cleaned_note=values.get("cleaned_note") or values.get("raw_input") or "",
        summary=values.get("summary") or "",
        key_takeaways=values.get("key_takeaways") or [],
        actionable_ideas=values.get("actionable_ideas") or [],
        tags=values.get("tags") or [],
        source_title=values.get("source_title"),
        source_creator=values.get("source_creator"),
        source_url=str(values["source_url"]) if values.get("source_url") else None,
        input_type=NoteInputType(values.get("input_type") or NoteInputType.TEXT),
        classification_confidence=Confidence(confidence),
        use_for_coaching=bool(values.get("use_for_coaching", False)),
        favorite=bool(values.get("favorite", False)),
        is_demo=bool(values.get("is_demo", False)),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_notes(
    db: Session,
    *,
    query: str | None = None,
    category: NoteCategory | None = None,
    tag: str | None = None,
    favorite: bool | None = None,
) -> list[models.TrainingNote]:
    statement = select(models.TrainingNote)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                models.TrainingNote.title.ilike(pattern),
                models.TrainingNote.cleaned_note.ilike(pattern),
                models.TrainingNote.summary.ilike(pattern),
            )
        )
    if category:
        statement = statement.where(models.TrainingNote.primary_category == category)
    if favorite is not None:
        statement = statement.where(models.TrainingNote.favorite == favorite)
    items = list(db.scalars(statement.order_by(models.TrainingNote.created_at.desc())))
    if tag:
        items = [item for item in items if tag.lower() in {value.lower() for value in item.tags}]
    return items


def note_public(item: models.TrainingNote) -> dict[str, Any]:
    return {
        "id": item.id,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "primary_category": item.primary_category.value,
        "title": item.title,
        "raw_input": item.raw_input,
        "cleaned_note": item.cleaned_note,
        "summary": item.summary,
        "key_takeaways": item.key_takeaways,
        "actionable_ideas": item.actionable_ideas,
        "tags": item.tags,
        "source_title": item.source_title,
        "source_creator": item.source_creator,
        "source_url": item.source_url,
        "input_type": item.input_type.value,
        "classification_confidence": item.classification_confidence.value,
        "use_for_coaching": item.use_for_coaching,
        "favorite": item.favorite,
        "is_demo": item.is_demo,
    }
