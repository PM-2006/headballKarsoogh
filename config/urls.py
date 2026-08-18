from django.urls import include, path

urlpatterns = [
    path("", include("game.urls")),
]
