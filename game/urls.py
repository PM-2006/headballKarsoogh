from django.urls import path
from . import views

app_name = "game"
urlpatterns = [
    path("", views.index, name="index"),
    path("healthz/", views.healthz, name="healthz"),
    path("api/vocabulary/", views.api_vocabulary, name="api_vocabulary"),
    path("api/validate/", views.api_validate_strategy, name="api_validate"),
    path("api/compile-strategy/", views.api_compile_strategy, name="api_compile_strategy"),
    path("api/strategies/", views.api_strategies, name="api_strategies"),
    path("api/strategies/<int:pk>/", views.api_strategy_detail, name="api_strategy_detail"),
    path("api/simulate/", views.api_simulate, name="api_simulate"),
    path("api/batch/", views.api_batch, name="api_batch"),
    path("api/game-active/", views.api_game_active, name="api_game_active"),
    path("api/session-limit/", views.api_session_limit, name="api_session_limit"),
    path("api/strategy-limit/", views.api_strategy_limit, name="api_strategy_limit"),
    path("api/strategy-strictness/", views.api_strategy_strictness, name="api_strategy_strictness"),
    path("api/game-config/", views.api_game_config, name="api_game_config"),
    path("api/game-config/reset/", views.api_game_config_reset, name="api_game_config_reset"),
    path("api/kit/", views.api_kit, name="api_kit"),
]
