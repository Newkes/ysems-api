from django.contrib import messages
from django.contrib.auth import get_user_model,login, logout , authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, FormView

from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser , JSONParser

from .forms import EntityForm, MembershipForm, SignupForm   
from .models import Entity, EntityMembership
from .permissions import CanEditEntity, CanViewEntity, IsEntityOwner, user_role_for_entity
from .storage_service import get_storage_service
from .serializers import (
    EntityCreateUpdateSerializer,
    EntityMembershipReadSerializer,
    EntitySerializer,
    MembershipCreateSerializer,
    MembershipUpdateSerializer,
    SignupSerializer,
)

User = get_user_model()



# API


class EntityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return (
            Entity.objects
            .filter(entitymembership__user=self.request.user)
            .distinct()
            .order_by("-date_created")
        )

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return EntityCreateUpdateSerializer
        return EntitySerializer

    def get_permissions(self):
        if self.action in ["list", "create"]:
            return [IsAuthenticated()]

        if self.action == "retrieve":
            return [IsAuthenticated(), CanViewEntity()]

        if self.action in ["update", "partial_update"]:
            return [IsAuthenticated(), CanEditEntity()]

        if self.action == "members":
            if self.request.method == "GET":
                return [IsAuthenticated(), CanViewEntity()]
            return [IsAuthenticated(), IsEntityOwner()]

        if self.action in ["update_member", "remove_member", "destroy"]:
            return [IsAuthenticated(), IsEntityOwner()]

        return [IsAuthenticated()]

    def perform_create(self, serializer):
        with transaction.atomic():
            entity = serializer.save()
            EntityMembership.objects.create(
                user=self.request.user,
                entity=entity,
                role="OWNER",
            )
        return entity

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = self.perform_create(serializer)

        output = EntitySerializer(entity, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        entity = self.get_object()

        if request.method.lower() == "get":
            memberships = (
                EntityMembership.objects
                .filter(entity=entity)
                .order_by("date_joined")
            )
            data = EntityMembershipReadSerializer(memberships, many=True).data
            return Response(data)

        serializer = MembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.get(id=serializer.validated_data["user_id"])
        role = serializer.validated_data["role"]

        if EntityMembership.objects.filter(entity=entity, user=user).exists():
            return Response(
                {"detail": "That user is already a member of this entity."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = EntityMembership.objects.create(
            entity=entity,
            user=user,
            role=role,
        )

        output = EntityMembershipReadSerializer(membership)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path=r"members/(?P<member_id>[^/.]+)")
    def update_member(self, request, pk=None, member_id=None):
        entity = self.get_object()

        try:
            membership = EntityMembership.objects.get(
                id=member_id,
                entity=entity,
            )
        except EntityMembership.DoesNotExist:
            return Response(
                {"detail": "Membership not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = MembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership.role = serializer.validated_data["role"]
        membership.save(update_fields=["role"])

        output = EntityMembershipReadSerializer(membership)
        return Response(output.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<member_id>[^/.]+)")
    def remove_member(self, request, pk=None, member_id=None):
        entity = self.get_object()

        try:
            membership = EntityMembership.objects.get(
                id=member_id,
                entity=entity,
            )
        except EntityMembership.DoesNotExist:
            return Response(
                {"detail": "Membership not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if membership.user == request.user and membership.role == "OWNER":
            owner_count = EntityMembership.objects.filter(
                entity=entity,
                role="OWNER",
            ).count()
            if owner_count <= 1:
                return Response(
                    {"detail": "You cannot remove the last remaining owner from this entity."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)

        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        token, _ = Token.objects.get_or_create(user=user)

        memberships = (
            EntityMembership.objects
            .filter(user=user)
            .select_related("entity")
            .order_by("date_joined")
        )

        entities_data = [
            {
                "id": str(m.entity.id),
                "true_name": m.entity.true_name,
                "role": m.role,
            }
            for m in memberships
        ]

        return Response(
            {
                "message": "Login successful.",
                "token": token.key,
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "entities": entities_data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = getattr(request, "auth", None)
        if token:
            token.delete()

        logout(request)

        return Response(
            {"message": "Logout successful."},
            status=status.HTTP_200_OK,
        )

class SignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result["user"]
        entity = result["entity"]
        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {
                "message": "Account created successfully.",
                "token": token.key,
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "entity": {
                    "id": str(entity.id),
                    "true_name": entity.true_name,
                },
            },
            status=status.HTTP_201_CREATED,
        )



# WEB / TEMPLATE VIEWS


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "entity/home.html"


class EntityListPageView(LoginRequiredMixin, ListView):
    model = Entity
    template_name = "entity/entity_list.html"
    context_object_name = "entities"

    def get_queryset(self):
        return (
            Entity.objects
            #.filter(entitymembership__user=self.request.user)
            .distinct()
            .order_by("-date_created")
        )


class EntityDetailPageView(LoginRequiredMixin, DetailView):
    model = Entity
    template_name = "entity/entity_detail.html"
    context_object_name = "entity"

    def get_queryset(self):
        return (
            Entity.objects
            .filter(entitymembership__user=self.request.user)
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entity = self.object
        context["memberships"] = (
            EntityMembership.objects
            .filter(entity=entity)
            .order_by("date_joined")
        )
        context["user_role"] = user_role_for_entity(self.request.user, entity)
        return context


class EntityCreatePageView(LoginRequiredMixin, CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "entity/entity_form.html"

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            EntityMembership.objects.create(
                user=self.request.user,
                entity=self.object,
                role="OWNER",
            )
        messages.success(self.request, "Entity created successfully.")
        return redirect("entity:web-entity-detail", pk=self.object.pk)


class EntityUpdatePageView(LoginRequiredMixin, UpdateView):
    model = Entity
    form_class = EntityForm
    template_name = "entity/entity_form.html"
    context_object_name = "entity"

    def get_queryset(self):
        return (
            Entity.objects
            .filter(entitymembership__user=self.request.user)
            .distinct()
        )

    def dispatch(self, request, *args, **kwargs):
        entity = self.get_object()
        role = user_role_for_entity(request.user, entity)
        if role not in ["OWNER", "MANAGER"]:
            return HttpResponseForbidden("You do not have permission to edit this entity.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Entity updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return f"/entities/{self.object.pk}/"


class EntityMembersPageView(LoginRequiredMixin, DetailView):
    model = Entity
    template_name = "entity/entity_members.html"
    context_object_name = "entity"

    def get_queryset(self):
        return (
            Entity.objects
            .filter(entitymembership__user=self.request.user)
            .distinct()
        )

    def dispatch(self, request, *args, **kwargs):
        entity = self.get_object()
        role = user_role_for_entity(request.user, entity)
        if role != "OWNER":
            return HttpResponseForbidden("Only owners can manage memberships.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = (
            EntityMembership.objects
            .filter(entity=self.object)
            .order_by("date_joined")
        )
        context["form"] = MembershipForm()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = MembershipForm(request.POST)

        if form.is_valid():
            membership = form.save(commit=False)
            membership.entity = self.object

            if EntityMembership.objects.filter(
                entity=self.object,
                user=membership.user,
            ).exists():
                messages.error(request, "That user is already a member of this entity.")
            else:
                membership.save()
                messages.success(request, "Member added successfully.")

            return redirect("entity:web-entity-members", pk=self.object.pk)

        context = self.get_context_data()
        context["form"] = form
        return self.render_to_response(context)


def remove_membership_page_view(request, pk, member_id):
    if not request.user.is_authenticated:
        return redirect("/admin/login/?next=/entities/")

    entity = get_object_or_404(
        Entity.objects.filter(entitymembership__user=request.user).distinct(),
        pk=pk,
    )

    role = user_role_for_entity(request.user, entity)
    if role != "OWNER":
        return HttpResponseForbidden("Only owners can remove memberships.")

    membership = get_object_or_404(
        EntityMembership,
        pk=member_id,
        entity=entity,
    )

    if membership.user == request.user and membership.role == "OWNER":
        owner_count = EntityMembership.objects.filter(entity=entity, role="OWNER").count()
        if owner_count <= 1:
            messages.error(request, "You cannot remove the last remaining owner.")
            return redirect("entity:web-entity-members", pk=entity.pk)

    membership.delete()
    messages.success(request, "Member removed successfully.")
    return redirect("entity:web-entity-members", pk=entity.pk)


class SignupPageView(FormView):
    template_name = "entity/signup.html"
    form_class = SignupForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("entity:web-entity-list")
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        username = form.cleaned_data["username"]
        email = form.cleaned_data.get("email", "")
        first_name = form.cleaned_data.get("first_name", "")
        last_name = form.cleaned_data.get("last_name", "")
        true_name = form.cleaned_data.get("true_name", "").strip()
        password = form.cleaned_data["password1"]

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

        login(self.request, user)
        return redirect("entity:web-entity-list")

   
