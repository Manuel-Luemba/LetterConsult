from typing import Optional, List

from ninja import Schema

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