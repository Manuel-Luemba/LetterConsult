from typing import Optional, List

from ninja import Schema, ModelSchema


from core.project.models import Project


class ProjectIn(Schema):
    name: str
    description: str = None
    cod_contractor: str
    cod_supervision: str
    cost_center: str
    localization: str
    is_active: Optional[bool] = None

class ProjectOut(ModelSchema):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'cod_contractor', 'cod_supervision', 'cost_center',
                        'localization', 'is_active']
        fields_optional = ['description']


class PaginatedProjectResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[ProjectOut]
