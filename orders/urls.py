from django.urls import path

from .views import (
    AdminAcceptAllOrdersView,
    AdminAcceptOrderView,
    AdminCancelOrderView,
    AdminCompleteOrderView,
    AdminOrderDetailView,
    AdminOrderListView,
    AdminRejectOrderView,
    CancelMyOrderView,
    CreateOrderView,
    DeleteMyOrderView,
    MyOrdersView,
    RestaurantAcceptOrderView,
    RestaurantCompleteOrderView,
    RestaurantDeleteOrderView,
    RestaurantOrderDetailView,
    RestaurantOrderListView,
    RestaurantRejectOrderView,
)

urlpatterns = [
    # User
    path("create/", CreateOrderView.as_view()),
    path("my/", MyOrdersView.as_view()),
    path("my/<int:pk>/cancel/", CancelMyOrderView.as_view()),
    path("my/<int:pk>/delete/", DeleteMyOrderView.as_view()),

    # Restaurant
    path("restaurant/", RestaurantOrderListView.as_view()),
    path("restaurant/<int:pk>/", RestaurantOrderDetailView.as_view()),
    path("restaurant/<int:pk>/accept/", RestaurantAcceptOrderView.as_view()),
    path("restaurant/<int:pk>/reject/", RestaurantRejectOrderView.as_view()),
    path("restaurant/<int:pk>/complete/", RestaurantCompleteOrderView.as_view()),
    path("restaurant/<int:pk>/delete/", RestaurantDeleteOrderView.as_view()),

    # Admin
    path("admin/", AdminOrderListView.as_view()),
    path("admin/accept-all/", AdminAcceptAllOrdersView.as_view()),
    path("admin/<int:pk>/", AdminOrderDetailView.as_view()),
    path("admin/<int:pk>/accept/", AdminAcceptOrderView.as_view()),
    path("admin/<int:pk>/reject/", AdminRejectOrderView.as_view()),
    path("admin/<int:pk>/complete/", AdminCompleteOrderView.as_view()),
    path("admin/<int:pk>/cancel/", AdminCancelOrderView.as_view()),
]