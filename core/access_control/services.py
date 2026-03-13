from django.contrib.auth.models import Group, Permission
from django.shortcuts import get_object_or_404
from django.db.models import Q
from math import ceil

def list_permissions():
    return Permission.objects.all()

def create_group(data):
    group = Group.objects.create(name=data.name)
    if data.permissions:
        group.permissions.set(data.permissions)
    return group

def update_group(group_id, data):
    group = get_object_or_404(Group, id=group_id)
    group.name = data.name
    group.save()

    group.permissions.set(data.permissions)
    return group

def delete_group(group_id):
    group = get_object_or_404(Group, id=group_id)
    group.delete()

def list_groups():
    return Group.objects.prefetch_related("permissions").all()

def get_group(group_id):
    return get_object_or_404(Group.objects.prefetch_related("permissions"), id=group_id)



def search_groups(search: str = None):
    qs = Group.objects.prefetch_related("permissions").all()

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
        )

    return qs


def paginate(queryset, page: int, page_size: int):
    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size

    items = list(queryset[start:end])
    total_pages = ceil(total / page_size) if page_size else 1

    return {

        "count": total,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "items": items

    }