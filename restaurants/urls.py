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

    # Reviews
    RestaurantReviewListView,
    AddRestaurantReviewView,
    ReviewRespondView,
    ReviewHelpfulView,
    ReviewDeleteView,
    MyReviewsView,
    EditMyReviewView,
    DeleteMyReviewView,
    FlagReviewView,

    # Admin review moderation
    AdminReviewListView,
    AdminHideReviewView,
    AdminDeleteReviewView,
    AdminClearFlagView,
)

urlpatterns = [
    # Admin restaurants
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

    # Public restaurants
    path("public/", PublicRestaurantListView.as_view()),
    path("public/<int:pk>/", PublicRestaurantDetailView.as_view()),

    # Public / User reviews
    path("<int:pk>/reviews/", RestaurantReviewListView.as_view()),
    path("<int:pk>/reviews/add/", AddRestaurantReviewView.as_view()),

    # User review management
    path("reviews/my/", MyReviewsView.as_view()),
    path("reviews/<int:review_id>/edit/", EditMyReviewView.as_view()),
    path("reviews/<int:review_id>/my-delete/", DeleteMyReviewView.as_view()),
    path("reviews/<int:review_id>/flag/", FlagReviewView.as_view()),
    path("reviews/<int:review_id>/helpful/", ReviewHelpfulView.as_view()),

    # Restaurant response only
    path("reviews/<int:review_id>/respond/", ReviewRespondView.as_view()),

    # Old admin delete review route
    path("reviews/<int:review_id>/delete/", ReviewDeleteView.as_view()),

    # Admin review moderation
    path("admin/reviews/", AdminReviewListView.as_view()),
    path("admin/reviews/<int:review_id>/hide/", AdminHideReviewView.as_view()),
    path("admin/reviews/<int:review_id>/delete/", AdminDeleteReviewView.as_view()),
    path("admin/reviews/<int:review_id>/clear-flag/", AdminClearFlagView.as_view()),
]