from django.urls import path
from .views import (
    SubmitFeedbackView,
    MyFeedbackListView,
    PublicFeedbackListView,
    AdminFeedbackListView,
    AdminFeedbackStatsView,
    AdminFeedbackDetailView,
    AdminFeedbackReplyView,
    AdminFeedbackToggleLikeView,
    AdminFeedbackStatusView,
)

urlpatterns = [
    # User / Public routes
    path('submit/', SubmitFeedbackView.as_view(), name='feedback-submit'),
    path('public/', PublicFeedbackListView.as_view(), name='feedback-public'),
    path('my/', MyFeedbackListView.as_view(), name='feedback-my'),

    # Super Admin management routes
    path('admin/', AdminFeedbackListView.as_view(), name='feedback-admin-list'),
    path('admin/stats/', AdminFeedbackStatsView.as_view(), name='feedback-admin-stats'),
    path('admin/<int:pk>/', AdminFeedbackDetailView.as_view(), name='feedback-admin-detail'),
    path('admin/<int:pk>/reply/', AdminFeedbackReplyView.as_view(), name='feedback-admin-reply'),
    path('admin/<int:pk>/toggle-like/', AdminFeedbackToggleLikeView.as_view(), name='feedback-admin-toggle-like'),
    path('admin/<int:pk>/status/', AdminFeedbackStatusView.as_view(), name='feedback-admin-status'),
]
