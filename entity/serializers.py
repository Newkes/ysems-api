from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.db import transaction

from .models import Entity, EntityMembership

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]


class EntityMembershipReadSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = EntityMembership
        fields = ["id", "user", "role", "date_joined"]


class EntitySerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = Entity
        fields = [
            "id",
            "true_name",
            "date_created",
            "basic_data_file_path",
            "memberships",
        ]
        read_only_fields = ["id", "date_created", "memberships"]

    def get_memberships(self, obj):
        memberships = (
            EntityMembership.objects
            .filter(entity=obj)
            .order_by("date_joined")
        )
        return EntityMembershipReadSerializer(memberships, many=True).data


class EntityCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = Entity
        fields = ["id", "true_name", "basic_data_file_path"]
        read_only_fields = ["id"]


class MembershipCreateSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    role = serializers.ChoiceField(
        choices=[choice[0] for choice in EntityMembership.ROLE_CHOICES]
    )

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User does not exist.")
        return value


class MembershipUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[choice[0] for choice in EntityMembership.ROLE_CHOICES]
    )

class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    true_name = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data["username"]
        email = validated_data.get("email", "")
        password = validated_data["password"]
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")
        true_name = validated_data.get("true_name", "").strip()

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        entity_name = true_name or " ".join(
            part for part in [first_name, last_name] if part
        ).strip() or username

        entity = Entity.objects.create(true_name=entity_name)

        EntityMembership.objects.create(
            user=user,
            entity=entity,
            role="OWNER",
        )

        return {
            "user": user,
            "entity": entity,
        }