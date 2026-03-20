from django import forms
from django.contrib.auth import get_user_model
from .models import Entity, EntityMembership

User = get_user_model()

class EntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["true_name", "visibility", "basic_data_file_path"]


class MembershipForm(forms.ModelForm):
    class Meta:
        model = EntityMembership
        fields = ["user", "role"]

class SignupForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    true_name = forms.CharField(max_length=255, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")

        return cleaned_data