from django.urls import path

from .views import (
    GlobalSearchView,
    SearchRestaurantsView,
    SearchDealsView,
    SearchHappyHoursView,
    MapDataView,
    MapCitiesView,
)

urlpatterns = [
    path("", GlobalSearchView.as_view()),
    path("restaurants/", SearchRestaurantsView.as_view()),
    path("deals/", SearchDealsView.as_view()),
    path("happy-hours/", SearchHappyHoursView.as_view()),
    path("map/", MapDataView.as_view()),
    path("map/cities/", MapCitiesView.as_view()),
]