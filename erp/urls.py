"""
URL configuration for erp project.

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
from django.shortcuts import redirect
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('attendance/', include('attendance.urls')),
    path('bot/', include('bot.urls')),
    path('grades/', include('grades.urls')),
    path('groups/', include('groups_app.urls')),
    path('payments/', include('payments.urls')),
    path('students/', include('students.urls')),
    path('users/', include('users1.urls')),
    path('reports/', include('reports.urls')),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'images/logo.png')),
    path('', lambda r: redirect('users1:index'), name='root_redirect'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
