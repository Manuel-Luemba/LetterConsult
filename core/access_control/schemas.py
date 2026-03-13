from ninja import Schema
from typing import List

class PermissionSchema(Schema):
    id: int
    name: str
    codename: str

class GroupIn(Schema):
    name: str
    permissions: List[int] = []

class GroupOut(Schema):
    id: int
    name: str
    permissions: List[PermissionSchema]

class PaginatedGroupResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[GroupOut]