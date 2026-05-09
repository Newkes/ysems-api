from django.contrib import messages
from django.contrib.auth import get_user_model,login, logout , authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView  # builtin django views

from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser , JSONParser

from urllib.parse import urlencode


#custom code
from .pagination import EntityPagination
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

responses = {
    "default": "You do not have permission to access this entity.",
    "fedit": "You do not have permission to edit this entity.",
    "fdelete": "You do not have permission to delete this entity.",
    "fmembers": "Only owners can manage memberships.",
}





# API


class EntityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = EntityPagination

    LIST_CACHE_TIMEOUT = 60
    MEMBERS_CACHE_TIMEOUT = 60

    def _user_entities_version_key(self, user_id):
        return f"entities:list:version:user:{user_id}"

    def _entity_members_version_key(self, entity_id):
        return f"entities:members:version:entity:{entity_id}"

    def _get_user_entities_version(self, user_id):
        return cache.get_or_set(self._user_entities_version_key(user_id), 1, None)

    def _get_entity_members_version(self, entity_id):
        return cache.get_or_set(self._entity_members_version_key(entity_id), 1, None)

    def _bump_user_entities_version(self, user_id):
        key = self._user_entities_version_key(user_id)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 2, None)

    def _bump_entity_members_version(self, entity_id):
        key = self._entity_members_version_key(entity_id)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 2, None)

    def _bump_entity_list_cache_for_members(self, entity):
        user_ids = EntityMembership.objects.filter(entity=entity).values_list("user_id", flat=True)
        for user_id in user_ids:
            self._bump_user_entities_version(str(user_id))

    def _normalized_query_string(self, request):
        items = []
        for key in sorted(request.query_params.keys()):
            values = request.query_params.getlist(key)
            for value in values:
                items.append((key, value))
        return urlencode(items)

    def _list_cache_key(self, request):
        user_id = str(request.user.id)
        version = self._get_user_entities_version(user_id)
        query_string = self._normalized_query_string(request)
        return f"entities:list:user:{user_id}:v:{version}:q:{query_string}"

    def _members_cache_key(self, entity):
        entity_id = str(entity.id)
        version = self._get_entity_members_version(entity_id)
        return f"entities:members:entity:{entity_id}:v:{version}"

    def list(self, request, *args, **kwargs):
        cache_key = self._list_cache_key(request)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            response = Response(cached_data)
            response["X-Cache"] = "HIT"
            response["X-Generated-At"] = cached_data.get("generated_at", "")
            return response

        response = super().list(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            data = dict(response.data)
            generated_at = timezone.now().isoformat()
            data["generated_at"] = generated_at

            cache.set(cache_key, data, self.LIST_CACHE_TIMEOUT)

            response = Response(data, status=status.HTTP_200_OK)
            response["X-Cache"] = "MISS"
            response["X-Generated-At"] = generated_at
            return response

        return response

    def get_queryset(self):
        qs = Entity.objects.all().distinct().order_by("-date_created")

        if not self.request.user.is_authenticated:
            return qs.filter(visibility="PUBLIC")

        return qs.filter(
            Q(visibility="PUBLIC") |
            Q(visibility="REGISTERED") |
            Q(visibility="RESTRICTED") |
            Q(visibility="HIDDEN") |
            Q(entitymembership__user=self.request.user)
        ).distinct()

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

        self._bump_user_entities_version(str(request.user.id))

        output = EntitySerializer(entity, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        entity = self.get_object()

        if request.method.lower() == "get":
            cache_key = self._members_cache_key(entity)
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)

            memberships = (
                EntityMembership.objects
                .filter(entity=entity)
                .order_by("date_joined")
            )
            data = EntityMembershipReadSerializer(memberships, many=True).data
            cache.set(cache_key, data, self.MEMBERS_CACHE_TIMEOUT)
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

        self._bump_entity_members_version(str(entity.id))
        self._bump_entity_list_cache_for_members(entity)
        self._bump_user_entities_version(str(user.id))

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

        self._bump_entity_members_version(str(entity.id))
        self._bump_entity_list_cache_for_members(entity)

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

        removed_user_id = str(membership.user_id)
        membership.delete()

        self._bump_entity_members_version(str(entity.id))
        self._bump_entity_list_cache_for_members(entity)
        self._bump_user_entities_version(removed_user_id)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_update(self, serializer):
        entity = serializer.save()
        self._bump_entity_members_version(str(entity.id))
        self._bump_entity_list_cache_for_members(entity)
        return entity

    def perform_destroy(self, instance):
        member_user_ids = [str(user_id) for user_id in EntityMembership.objects.filter(entity=instance).values_list("user_id", flat=True)]
        entity_id = str(instance.id)
        instance.delete()

        cache.delete(self._entity_members_version_key(entity_id))
        for user_id in member_user_ids:
            self._bump_user_entities_version(user_id)

class LoginAPIView(APIView):
    authentication_classes = []
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





def create_entity_with_owner(user, *, true_name=None, form=None):
    with transaction.atomic():
        if form is not None:
            entity = form.save()
        else:
            entity = Entity.objects.create(true_name=true_name)

        EntityMembership.objects.create(
            user=user,
            entity=entity,
            role="OWNER",
        )

    return entity

class entityObjectContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_role"] = user_role_for_entity(self.request.user, self.object)
        return context

class entitymixin(LoginRequiredMixin):
    required_roles = None
    forbidden_message_key = "default"
    use_member_queryset = True
    success_message = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entities"] = (
            Entity.objects
            .distinct()
            .order_by("-date_created")
        )
        return context

    def get_queryset(self):
        if self.use_member_queryset:
            return (
                Entity.objects
                #.filter(entitymembership__user=self.request.user)
                .distinct()
            )
        return (
            Entity.objects
            .distinct()
            .order_by("-date_created")
        )

    def dispatch(self, request, *args, **kwargs):
        if self.required_roles is not None:
            entity = self.get_object()
            role = user_role_for_entity(request.user, entity)

            if role not in self.required_roles:
                return HttpResponseForbidden(
                    responses[self.forbidden_message_key]
                )

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if self.success_message:
            messages.success(self.request, self.success_message)
        return super().form_valid(form)


class HomeView(entitymixin, TemplateView):
    template_name = "entity/home.html"
    use_member_queryset = False

    def get_context_data(self, **kwargs):
        context = TemplateView.get_context_data(self, **kwargs)
        context["entities"] = (
            Entity.objects
            .distinct()
            .order_by("-date_created")
        )
        return context


class EntityListPageView(entitymixin, ListView):
    model = Entity
    template_name = "entity/entity_list.html"
    context_object_name = "entities"
    use_member_queryset = False


class EntityDetailPageView(entitymixin, entityObjectContextMixin, DetailView):
    model = Entity
    template_name = "entity/entity_detail.html"
    context_object_name = "entity"


class EntityCreatePageView(entitymixin, CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "entity/entity_form.html"
    use_member_queryset = False
    success_message = "Entity created successfully."

    def form_valid(self, form):
        self.object = create_entity_with_owner(
            self.request.user,
            form=form,
        )
        if self.success_message:
            messages.success(self.request, self.success_message)
        return redirect("entity:web-entity-detail", pk=self.object.pk)


class EntityUpdatePageView(entitymixin, entityObjectContextMixin, UpdateView):
    model = Entity
    form_class = EntityForm
    template_name = "entity/entity_form.html"
    context_object_name = "entity"

    required_roles = ["OWNER", "MANAGER"]
    forbidden_message_key = "fedit"
    success_message = "Entity updated successfully."

    def get_success_url(self):
        return f"/entities/{self.object.pk}/"


class EntityDeleteView(entitymixin, entityObjectContextMixin, DeleteView):
    model = Entity
    template_name = "entity/entity_confirm_delete.html"
    context_object_name = "entity"
    success_url = reverse_lazy("entity:home")

    required_roles = ["OWNER"]
    forbidden_message_key = "fdelete"
    success_message = "Entity deleted successfully."


class EntityMembersPageView(entitymixin, entityObjectContextMixin, DetailView):
    model = Entity
    template_name = "entity/entity_members.html"
    context_object_name = "entity"

    required_roles = ["OWNER"]
    forbidden_message_key = "fmembers"

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


class SignupPageView(FormView):
    template_name = "entity/signup.html"
    form_class = SignupForm

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

        create_entity_with_owner(
            user,
            true_name=entity_name,
        )

        login(self.request, user)
        return redirect("entity:web-entity-list")