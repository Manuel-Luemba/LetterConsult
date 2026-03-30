from ninja import Schema
from typing import List, Optional

from pydantic import Field
from datetime import datetime

from core.access_control.schemas import GroupOut


class ChangePasswordIn(Schema):
    old_password: str
    new_password: str

class AuthInput(Schema):
    username: str
    password: str

class AuthOutput(Schema):
    access: str
    refresh: str

class UserCreateIn(Schema):
    username: str
    email: str
    first_name: str
    last_name: str
    image: Optional[str] = None
    password: str  # obrigatório somente no CREATE
    is_active: bool = True
    department_id: int | None = None
    position_id: int | None = None
    groups_ids: List[int] = Field(default_factory=list)

class UserUpdateIn(Schema):
    username: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None  # <<< chave do problema
    image: Optional[str] = None
    is_active: Optional[bool] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    groups_ids: Optional[List[int]] = None

class UserOut(Schema):
    id: int
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    full_name: Optional[str] = Field(default=None, description="Nome completo")

    image: Optional[str] = Field(default=None, description="URL da foto")

    department_id: Optional[int] = None
    department_name: Optional[str] = None

    position_id: Optional[int] = None
    position_name: Optional[str] = None   # descomente se quiser

    date_joined: Optional[str] = None

    groups: List[GroupOut] = Field(default_factory=list, description="Grupos do usuário")

    class Meta:
        #orm_mode = True
        from_attributes = True
        # Permite acessar por nome de campo mesmo com alias (opcional)
        # allow_population_by_field_name = True

    # The following property is typically defined on the ORM model, not the Pydantic schema.
    # If the intent is to expose this property via the schema, it should be added as a field
    # in the schema and populated within the `from_orm` method, assuming the ORM model
    # has an `is_approver` property.
    # For now, I will add it as a field to UserOut and UserSchema, and assume the ORM model
    # will provide this attribute.

    @staticmethod
    def resolve_full_name(obj):
        return obj.get_full_name() if hasattr(obj, 'get_full_name') else f"{getattr(obj, 'first_name', '')} {getattr(obj, 'last_name', '')}".strip()

    @staticmethod
    def resolve_image(obj):
        if hasattr(obj, 'image') and obj.image:
            try:
                return obj.image.url
            except:
                return None
        return None

    @staticmethod
    def resolve_department_name(obj):
        return obj.department.name if obj.department else None

    @staticmethod
    def resolve_department_id(obj):
        return obj.department_id

    @staticmethod
    def resolve_position_name(obj):
        return obj.position.name if obj.position else None

    @staticmethod
    def resolve_position_id(obj):
        return obj.position_id

    @staticmethod
    def resolve_date_joined(obj):
        return obj.date_joined.strftime("%d/%m/%Y") if obj.date_joined else None

class PaginatedUserResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[UserOut]

class EmployeeWorkSettingsIn(Schema):
    weekly_hours_target: float
    daily_hours_target: float
    preferred_work_days: str

class EmployeeWorkSettingsOut(Schema):
    id: int
    employee_id: int
    weekly_hours_target: float
    daily_hours_target: float
    preferred_work_days: str


class HRProfileOut(Schema):
    cpf: str
    salario: float
    beneficios: Optional[str]

class PurchaseProfileOut(Schema):
    limite_aprovacao: float
    centro_compras: str

class UserSchema(Schema):
    id: int
    username: str
    email: Optional[str] = None  # Torne opcional
    first_name: Optional[str] = None  # Torne opcional
    last_name: Optional[str] = None  # Torne opcional
    groups: List[str] = []
    image: Optional[str] = None  # Torne opcional
    full_name: Optional[str] = None
    
    # Flags de permissão (extraídas das properties do model)
    is_approver: bool = False
    is_manager: bool = False
    is_director: bool = False
    is_purchasing_central: bool = False
    is_administrator: bool = False
    is_project_responsible: bool = False
    is_team_leader: bool = False

    @classmethod
    def from_orm(cls, user):
        data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,  # Agora pode ser None
            'first_name': user.first_name,  # Agora pode ser None
            'last_name': user.last_name,  # Agora pode ser None
            'full_name': user.get_full_name(),  # Agora pode ser None
            'groups': list(user.groups.values_list('name', flat=True)),
            # Preencher flags
            'is_approver': user.is_approver,
            'is_manager': user.is_manager,
            'is_director': user.is_director,
            'is_purchasing_central': user.is_purchasing_central,
            'is_administrator': user.is_administrator,
            'is_project_responsible': user.is_project_responsible,
            'is_team_leader': user.is_team_leader,
        }

        # Adicione sempre o campo image
        if hasattr(user, 'image') and user.image:
            try:
                data['image'] = user.image.url
            except:
                data['image'] = None
        else:
            data['image'] = None

        return cls(**data)