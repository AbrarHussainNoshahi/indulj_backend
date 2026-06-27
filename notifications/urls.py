from django.urls import path
from .views import (
    NotificationListView,
    NotificationUnreadCountView,
    MarkAllReadView,
    ClearAllView,
    MarkReadView,
    DeleteNotificationView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('mark-all-read/', MarkAllReadView.as_view(), name='notification-mark-all-read'),
    path('clear-all/', ClearAllView.as_view(), name='notification-clear-all'),
    path('<int:pk>/read/', MarkReadView.as_view(), name='notification-read'),
    path('<int:pk>/mark-read/', MarkReadView.as_view(), name='notification-mark-read'),
    path('<int:pk>/delete/', DeleteNotificationView.as_view(), name='notification-delete'),
]
