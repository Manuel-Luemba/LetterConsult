from typing import Optional, List

from ninja import Schema, Field

class PositionOut(Schema):  # opcional
    id: int
    name: str


class PositionIn(Schema):
    name: str
    desc: Optional[str] = None

class PaginatedPositionResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[PositionOut]


class ContactIn(Schema):
    full_name: str = Field(..., max_length=150)
    email: str = Field(..., max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    message: str = Field(..., max_length=2000)
    website: Optional[str] = None  # Honeypot field