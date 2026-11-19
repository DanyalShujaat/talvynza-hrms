"""Pagination / sorting helpers shared by list endpoints."""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
        self.page, self.page_size = page, page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
    return list(rows), total
