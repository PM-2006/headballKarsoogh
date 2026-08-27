from django.urls import path
from . import views

app_name = "game"
urlpatterns = [
    path("", views.index, name="index"),
    path("api/vocabulary/", views.api_vocabulary, name="api_vocabulary"),
    path("api/validate/", views.api_validate_strategy, name="api_validate"),
    path("api/compile-strategy/", views.api_compile_strategy, name="api_compile_strategy"),
    path("api/strategies/", views.api_strategies, name="api_strategies"),
    path("api/strategies/<int:pk>/", views.api_strategy_detail, name="api_strategy_detail"),
    path("api/simulate/", views.api_simulate, name="api_simulate"),
    path("api/batch/", views.api_batch, name="api_batch"),
]
