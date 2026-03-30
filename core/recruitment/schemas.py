from typing import Optional, List
from ninja import Schema
from datetime import datetime

class VacancyOut(Schema):
    id: int
    title: str
    description: str
    requirements: str
    responsibilities: str
    location: str
    salary_range: Optional[str]
    education_level: str
    is_active: bool

class VacancyIn(Schema):
    title: str
    description: str
    requirements: str
    responsibilities: str
    location: str
    salary_range: Optional[str] = None
    education_level: str
    is_active: bool = True

class ApplicationIn(Schema):
    vacancy_id: int
    full_name: str
    email: str
    phone: str
    academic_degree: str
    message: Optional[str]
