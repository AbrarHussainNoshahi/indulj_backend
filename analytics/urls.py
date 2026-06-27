from django.urls import path

from .views import (
    AdminDashboardStatsView,
    AdminPlatformSummaryView,
    AdminRestaurantAnalyticsView,
    AdminRestaurantEarningsView,
    AdminRevenueChartView,
    AdminRevenueSourcesView,
    AdminSubmissionsChartView,
    AdminUserGrowthView,
    RestaurantAnalyticsSummaryView,
    RestaurantDashboardStatsView,
    UserAnalyticsSummaryView,
    UserDashboardStatsView,
    AdminRevenueOrdersTrendView,
    AdminDealsHappyHoursChartView,
    RestaurantRevenueOrdersTrendView,
    RestaurantOptimizedDealsView,
    RestaurantDealsPerformanceView,
    RestaurantHappyHoursAttendanceView,
    AdminRecentActivityExportView,
    AdminRecentActivityView,
    RestaurantRecentActivityView,
    RestaurantRecentActivityExportView
)

urlpatterns = [
    # Admin
    path("admin/stats/", AdminDashboardStatsView.as_view()),
    path("admin/summary/", AdminPlatformSummaryView.as_view()),
    path("admin/revenue/", AdminRevenueChartView.as_view()),
    path("admin/revenue-sources/", AdminRevenueSourcesView.as_view()),
    path("admin/submissions/", AdminSubmissionsChartView.as_view()),
    path("admin/user-growth/", AdminUserGrowthView.as_view()),
    path("admin/restaurant-earnings/", AdminRestaurantEarningsView.as_view()),
    path("admin/restaurant/<int:pk>/", AdminRestaurantAnalyticsView.as_view()),
    path("admin/revenue-orders/", AdminRevenueOrdersTrendView.as_view()),
    path("admin/deals-hh/", AdminDealsHappyHoursChartView.as_view()),
    path("admin/recent-activity/", AdminRecentActivityView.as_view()),
    path("admin/recent-activity/export/", AdminRecentActivityExportView.as_view()),



    # Restaurant
    path("restaurant/revenue-orders/", RestaurantRevenueOrdersTrendView.as_view()),
    path("restaurant/optimized-deals/", RestaurantOptimizedDealsView.as_view()),
    path("restaurant/deals-performance/", RestaurantDealsPerformanceView.as_view()),
    path("restaurant/hh-attendance/", RestaurantHappyHoursAttendanceView.as_view()),
    path("restaurant/stats/", RestaurantDashboardStatsView.as_view()),
    path("restaurant/summary/", RestaurantAnalyticsSummaryView.as_view()),
    path("restaurant/recent-activity/", RestaurantRecentActivityView.as_view()),
    path("restaurant/recent-activity/export/", RestaurantRecentActivityExportView.as_view()),

    # User
    path("user/stats/", UserDashboardStatsView.as_view()),
    path("user/summary/", UserAnalyticsSummaryView.as_view()),
]