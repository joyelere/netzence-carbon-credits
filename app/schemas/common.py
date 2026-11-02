"""Shapes shared by several endpoints."""

from pydantic import BaseModel


class Pagination(BaseModel):
    """Same shape as Laravel's paginate() meta."""

    current_page: int
    per_page: int
    total: int
    last_page: int

    @classmethod
    def build(cls, page: int, per_page: int, total: int) -> "Pagination":
        return cls(
            current_page=page,
            per_page=per_page,
            total=total,
            last_page=max(1, -(-total // per_page)),  # ceil division
        )
