from rest_framework.permissions import BasePermission

from .models import EntityMembership


def get_membership(user, entity):
    if not user or not user.is_authenticated:
        return None
    return EntityMembership.objects.filter(user=user, entity=entity).first()


def user_role_for_entity(user, entity):
    membership = get_membership(user, entity)
    return membership.role if membership else None


class CanViewEntity(BasePermission):
    """
    User must be a member of the entity to view it.
    """

    def has_object_permission(self, request, view, obj):
        return EntityMembership.objects.filter(
            user=request.user,
            entity=obj
        ).exists()


class CanEditEntity(BasePermission):
    """
    OWNER and MANAGER can update entity fields.
    """

    def has_object_permission(self, request, view, obj):
        role = user_role_for_entity(request.user, obj)
        return role in ["OWNER", "MANAGER"]


class IsEntityOwner(BasePermission):
    """
    Only OWNER can delete entities or manage memberships.
    """

    def has_object_permission(self, request, view, obj):
        role = user_role_for_entity(request.user, obj)
        return role == "OWNER"