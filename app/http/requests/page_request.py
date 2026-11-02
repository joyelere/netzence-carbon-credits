from pydantic import BaseModel, Field


class PageRequest(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class PendingCancellationsRequest(PageRequest):
    older_than_hours: int = Field(48, ge=0, le=24 * 365)
