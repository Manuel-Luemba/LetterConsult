from typing import List, Optional
from ninja import Schema
from core.erp.models import Department
from pydantic import BaseModel


class DepartmentIn(Schema):
    name: str
    desc: Optional[str] = None
    abbreviation: Optional[str] = None
    manager: Optional[int] = None
    managers: List[int] = []
    deputy_managers: List[int] = []
    cost_center: str
    is_active: Optional[bool] = None

class DepartmentOut(BaseModel):
    id: int
    name: str
    abbreviation: Optional[str] = None
    desc: Optional[str] = None
    cost_center: Optional[str] = None
    is_active: Optional[bool] = None

    manager: Optional[int] = None
    manager_name: Optional[str] = None

    managers: List[int] = []
    manager_names: List[str] = []

    deputy_managers: List[int] = []
    deputy_manager_names: List[str] = []

    @classmethod
    def from_orm(cls, obj: Department):
        return cls(
            id=obj.id,
            name=obj.name,
            abbreviation=obj.abbreviation,
            desc=obj.desc,
            cost_center=obj.cost_center,
            is_active=obj.is_active,
            manager=obj.manager.id if obj.manager else None,
            manager_name=obj.manager.get_full_name() if obj.manager else None,
            managers=[m.id for m in obj.managers.all()],
            manager_names=[m.get_full_name() for m in obj.managers.all()],
            deputy_managers=[dm.id for dm in obj.deputy_managers.all()],
            deputy_manager_names=[dm.get_full_name() for dm in obj.deputy_managers.all()],
        )

    # class Config:
    #     model = Department
    #     model_fields = [
    #         'id', 'name', 'desc', 'abbreviation',
    #         'manager', 'cost_center', 'is_active',
    #         'managers', 'deputy_managers'
    #     ]

class PaginatedDepartmentResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[DepartmentOut]