from django.urls import path

from .views import (
    PublicDealListView,
    PublicDealDetailView,
    MapDealsView,
    TrackDealView,

    SubmitDealView,
    MyDealsView,
    DeleteMyDealView,
    SaveDealView,
    UnsaveDealView,
    SavedDealsView,

    RestaurantDealListView,
    RestaurantCreateDealView,
    RestaurantUpdateDeleteDealView,

    AdminCreateDealView,
    AdminDealListView,
    AdminApproveDealView,
    AdminToggleHotDealView,
    AdminRejectDealView,
    AdminAcceptAllDealsView,
    AdminDeleteDealView,
)

urlpatterns = [
    # Public
    path("public/", PublicDealListView.as_view()),
    path("public/map/", MapDealsView.as_view()),
    path("public/<int:pk>/", PublicDealDetailView.as_view()),

    # User
    path("submit/", SubmitDealView.as_view()),
    path("my-deals/", MyDealsView.as_view()),
    path("saved/", SavedDealsView.as_view()),
    path("<int:pk>/save/", SaveDealView.as_view()),
    path("<int:pk>/unsave/", UnsaveDealView.as_view()),
    path("<int:pk>/delete/", DeleteMyDealView.as_view()),
    path("<int:pk>/track-view/", TrackDealView.as_view()),

    # Restaurant
    path("restaurant/", RestaurantDealListView.as_view()),
    path("restaurant/create/", RestaurantCreateDealView.as_view()),
    path("restaurant/<int:pk>/update/", RestaurantUpdateDeleteDealView.as_view()),
    path("restaurant/<int:pk>/delete/", RestaurantUpdateDeleteDealView.as_view()),

    # Admin
    path("admin/", AdminDealListView.as_view()),
    path("admin/create/", AdminCreateDealView.as_view()),
    path("admin/accept-all/", AdminAcceptAllDealsView.as_view()),
    path("admin/<int:pk>/approve/", AdminApproveDealView.as_view()),
    path("admin/<int:pk>/reject/", AdminRejectDealView.as_view()),
    path("admin/<int:pk>/delete/", AdminDeleteDealView.as_view()),
    path("admin/<int:pk>/toggle-hot/", AdminToggleHotDealView.as_view()),
]