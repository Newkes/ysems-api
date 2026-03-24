from django.urls import include, path
from rest_framework.routers import DefaultRouter
from django.contrib.auth.views import LoginView, LogoutView
#internal file imports
from .views import (
    EntityCreatePageView,
    EntityDetailPageView,
    EntityListPageView,
    EntityMembersPageView,
    EntityUpdatePageView,
    EntityViewSet,
    HomeView,
    remove_membership_page_view,
    SignupAPIView,
    SignupPageView,
    LoginAPIView,
    LogoutAPIView,
    
)

app_name = "entity"

router = DefaultRouter()
router.register(r"entities", EntityViewSet, basename="entity-api")

urlpatterns = [
    #web app end points
    path("login/", LoginView.as_view(template_name="entity/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="/login/"), name="logout"),
    path("signup/", SignupPageView.as_view(), name="signup"),
   
    path("", HomeView.as_view(), name="home"),
    # shared between web and api
    path("entities/",                                           EntityListPageView.as_view(),    name="web-entity-list"),
    path("entities/create/",                                    EntityCreatePageView.as_view(),  name="web-entity-create"),
    path("entities/<str:pk>/",                                  EntityDetailPageView.as_view(),  name="web-entity-detail"),
    path("entities/<str:pk>/edit/",                             EntityUpdatePageView.as_view(),  name="web-entity-edit"),
    path("entities/<str:pk>/members/",                          EntityMembersPageView.as_view(), name="web-entity-members"),
    path("entities/<str:pk>/members/<str:member_id>/remove/",   remove_membership_page_view,     name="web-entity-member-remove"),

    #api endpoints (desktop and mobile)
    path("api/signup/", SignupAPIView.as_view(), name="api-signup"),
    path("api/login/", LoginAPIView.as_view(), name="api-login"),
    path("api/logout/", LogoutAPIView.as_view(), name="api-login"),

    path("api/", include(router.urls)),


]