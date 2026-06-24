from django.urls import path

from .views import (
    AdminAcceptAllHappyHoursView,
    AdminAcceptHappyHourView,
    AdminHappyHourDetailView,
    AdminHappyHourListView,
    AdminRejectHappyHourView,
    DeleteMyHappyHourView,
    MapHappyHoursView,
    MyHappyHoursView,
    PlanHappyHourView,
    CancelMyHappyHourView,
    PublicHappyHourDetailView,
    PublicHappyHourListView,
    RestaurantAcceptAllHappyHoursView,
    RestaurantAcceptHappyHourView,
    RestaurantCreateHappyHourView,
    RestaurantHappyHourListView,
    RestaurantRejectHappyHourView,
    RestaurantUpdateDeleteHappyHourView,
)

urlpatterns = [
    # Public
    path("public/", PublicHappyHourListView.as_view()),
    path("public/map/", MapHappyHoursView.as_view()),
    path("public/<int:pk>/", PublicHappyHourDetailView.as_view()),
    path("<int:pk>/cancel/", CancelMyHappyHourView.as_view()),

    # User
    path("plan/", PlanHappyHourView.as_view()),
    path("my/", MyHappyHoursView.as_view()),
    path("<int:pk>/delete/", DeleteMyHappyHourView.as_view()),

    # Restaurant
    path("restaurant/", RestaurantHappyHourListView.as_view()),
    path("restaurant/create/", RestaurantCreateHappyHourView.as_view()),
    path("restaurant/accept-all/", RestaurantAcceptAllHappyHoursView.as_view()),
    path("restaurant/<int:pk>/update/", RestaurantUpdateDeleteHappyHourView.as_view()),
    path("restaurant/<int:pk>/delete/", RestaurantUpdateDeleteHappyHourView.as_view()),
    path("restaurant/<int:pk>/accept/", RestaurantAcceptHappyHourView.as_view()),
    path("restaurant/<int:pk>/reject/", RestaurantRejectHappyHourView.as_view()),

    # Admin
    path("admin/", AdminHappyHourListView.as_view()),
    path("admin/accept-all/", AdminAcceptAllHappyHoursView.as_view()),
    path("admin/<int:pk>/", AdminHappyHourDetailView.as_view()),
    path("admin/<int:pk>/accept/", AdminAcceptHappyHourView.as_view()),
    path("admin/<int:pk>/reject/", AdminRejectHappyHourView.as_view()),
]