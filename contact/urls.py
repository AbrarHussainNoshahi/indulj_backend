from django.urls import path
from .views import (
    ContactMessageCreateView,
    AdminContactMessageListView,
    AdminContactMessageDetailView,
)

urlpatterns = [
    # Public & authenticated contact submission
    path("", ContactMessageCreateView.as_view(), name="contact-submit"),

    # SuperAdmin management routes
    path("admin/", AdminContactMessageListView.as_view(), name="contact-admin-list"),
    path("admin/<int:pk>/", AdminContactMessageDetailView.as_view(), name="contact-admin-detail"),
]
