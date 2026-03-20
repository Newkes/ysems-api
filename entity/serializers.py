from django.contrib.auth import get_user_model
from rest_framework import serializers

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