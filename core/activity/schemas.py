from typing import List, Optional
from ninja import Schema, ModelSchema
from core.activity.models import Activity
from core.timesheet.schemas import DepartmentOut


class ActivityIn(Schema):
    name: str
    description: str = None
    department: int
    is_active: Optional[bool] = None

class ActivityOut(ModelSchema):
    department: DepartmentOut  # Aqui está a chave!

    class Meta:
        model = Activity
        fields = ['id', 'name', 'description', 'department', 'is_active']
        fields_optional = ['description']

class PaginatedActivityResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[ActivityOut]
