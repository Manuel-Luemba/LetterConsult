# utils/api_errors.py
from django.http import JsonResponse

def create_error_response(message: str, status: int = 400):
    return JsonResponse({
        'error': True,
        'message': message,
        'status': status
    }, status=status)


def get_user_permission_level(user):
    """Retorna o nível de permissão do usuário"""
    if getattr(user, 'is_superuser', False):
        return 'admin'
    elif hasattr(user, 'managed_department'):
        return 'manager'
    else:
        return 'regular'

def get_user_permission_level(user):
    """Retorna o nível de permissão baseado nos grupos"""
    user_groups = user.groups.values_list('name', flat=True)

    if 'Gestão' in user_groups:
        return 'gestao'  # Máximo poder
    elif 'RH' in user_groups:
        return 'rh'  # Acesso total igual à Gestão
    elif 'Gestores' in user_groups:
        return 'gestor'  # Poder departamental
    elif 'Colaborador' in user_groups:
        return 'colaborador'  # Poder individual
    else:
        return 'colaborador'  # Default seguro

def can_user_manage_employee(request_user, target_employee):
    """Verifica se usuário pode gerenciar outro employee"""
    permission_level = get_user_permission_level(request_user)

    if permission_level in ['gestao', 'rh']:
        return True, None  # Gestão e RH têm acesso total

    elif permission_level == 'gestor':
        # Verificar se gestor tem departamento e se employee pertence a ele
        if not hasattr(request_user, 'managed_department') or not request_user.managed_department:
            return False, "Gestor não possui departamento associado"

        if not target_employee.department:
            return False, "Employee não possui departamento"

        if target_employee.department == request_user.managed_department:
            return True, None
        else:
            return False, f"Acesso restrito ao departamento {request_user.managed_department.name}"

    else:  # colaborador
        if request_user == target_employee:
            return True, None
        else:
            return False, "Colaboradores só podem gerenciar próprios dados"

def validate_timesheet(tasks):
    daily_totals = {}

    for task in tasks:
        date = task['date_creation']
        hours = task['hour_total']

        # Soma horas por data
        if date not in daily_totals:
            daily_totals[date] = 0
        daily_totals[date] += hours

        # Verifica se excede 24h em alguma data
        if daily_totals[date] > 16:
            return False, f"Dia {date} excede 16h: {daily_totals[date]}h"

    return True, daily_totals