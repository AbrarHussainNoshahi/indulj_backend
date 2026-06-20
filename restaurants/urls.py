from django.urls import path

from .views import (
    AdminRestaurantListView,
    AdminCreateRestaurantView,
    AdminRestaurantDetailView,
    AdminSuspendRestaurantView,
    MyRestaurantView,
    MyRestaurantGalleryView,
    PublicRestaurantListView,
    PublicRestaurantDetailView,
    ReviewListAddView,
    ReviewRespondView,
    ReviewHelpfulView,
    ReviewDeleteView,
)

urlpatterns = [
    # Admin
    path("", AdminRestaurantListView.as_view()),
    path("create/", AdminCreateRestaurantView.as_view()),
    path("<int:pk>/", AdminRestaurantDetailView.as_view()),
    path("<int:pk>/update/", AdminRestaurantDetailView.as_view()),
    path("<int:pk>/delete/", AdminRestaurantDetailView.as_view()),
    path("<int:pk>/suspend/", AdminSuspendRestaurantView.as_view()),

    # Restaurant owner
    path("my-restaurant/", MyRestaurantView.as_view()),
    path("my-restaurant/update/", MyRestaurantView.as_view()),
    path("my-restaurant/gallery/add/", MyRestaurantGalleryView.as_view()),
    path(
        "my-restaurant/gallery/<int:image_id>/",
        MyRestaurantGalleryView.as_view(),
    ),

    # Public
    path("public/", PublicRestaurantListView.as_view()),
    path("public/<int:pk>/", PublicRestaurantDetailView.as_view()),

    # Reviews
    path("<int:pk>/reviews/", ReviewListAddView.as_view()),
    path("<int:pk>/reviews/add/", ReviewListAddView.as_view()),
    path("reviews/<int:review_id>/respond/", ReviewRespondView.as_view()),
    path("reviews/<int:review_id>/helpful/", ReviewHelpfulView.as_view()),
    path("reviews/<int:review_id>/delete/", ReviewDeleteView.as_view()),
]