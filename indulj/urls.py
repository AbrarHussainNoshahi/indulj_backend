"""
URL configuration for indulj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.views.decorators.clickjacking import xframe_options_exempt


@xframe_options_exempt
def serve_media_with_cors(request, path, document_root=None, show_indexes=False):
    response = serve(request, path, document_root=document_root, show_indexes=show_indexes)
    response["Access-Control-Allow-Origin"] = "*"
    return response


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/restaurants/', include('restaurants.urls')),
    path('api/deals/', include('deals.urls')),
    path('api/happy-hours/', include('happy_hours.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/analytics/', include('analytics.urls')),
    path("api/search/", include("search.urls")),
    path('api/feedback/', include('feedback.urls')),
    path('api/contact/', include('contact.urls')),
    # Always serve media files (documents, PDF menus, uploads) from local VPS MEDIA_ROOT
    re_path(r"^media/(?P<path>.*)$", serve_media_with_cors, {"document_root": settings.MEDIA_ROOT}),
]