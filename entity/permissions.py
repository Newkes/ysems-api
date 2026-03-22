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
    def has_object_permission(self, request, view, obj):
        role = user_role_for_entity(request.user, obj)
        if role:
            return True

        if obj.is_hidden or obj.visibility == "HIDDEN":
            return False

        if obj.visibility == "PUBLIC":
            return True

        if obj.visibility == "REGISTERED":
            return request.user.is_authenticated

        if obj.visibility == "RESTRICTED":
            return False

        return False



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