from django.contrib import admin
from .models import Entity, EntityMembership

# This lets you add Users to an Entity directly on the Entity's page
class MembershipInline(admin.TabularInline):
    model = EntityMembership
    extra = 1

@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    # Removed 'get_user_status' because 'user' is no longer a single field
    list_display = ('true_name', 'date_created')
    inlines = [MembershipInline]

@admin.register(EntityMembership)
class EntityMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'entity', 'role', 'date_joined')
