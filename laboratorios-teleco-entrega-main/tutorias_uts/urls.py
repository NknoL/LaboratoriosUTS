from django.contrib.auth import views as auth_views
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView


def salud(request):
    return JsonResponse({"status": "ok"})


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


urlpatterns = [
    path("salud/", salud),
    path("robots.txt", robots),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("admin/", RedirectView.as_view(pattern_name="reportes", permanent=False)),
    path(
        "cuentas/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("cuentas/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("tutorias.urls")),
]
