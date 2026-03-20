from django import forms

from .models import Entity, EntityMembership


class EntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["true_name", "visibility", "basic_data_file_path"]


class MembershipForm(forms.ModelForm):
    class Meta:
        model = EntityMembership
        fields = ["user", "role"]