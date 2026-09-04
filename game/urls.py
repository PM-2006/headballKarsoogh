from django.urls import path
from . import views
from . import views_messaging as inbox
from . import views_bracket

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

    # --- Inbox: any signed-in user reads their own notifications ---
    path("api/notifications/", inbox.api_notifications, name="api_notifications"),
    path("api/notifications/read/", inbox.api_notifications_read, name="api_notifications_read"),
    path("api/notifications/read-all/", inbox.api_notifications_read_all, name="api_notifications_read_all"),
    # Last of the notifications routes: "read/" and "read-all/" must match
    # before this one, or they would be read as a message id.
    path("api/notifications/<int:pk>/", inbox.api_notification_detail, name="api_notification_detail"),

    # --- Composer: admins only ---
    path("api/messages/", inbox.api_messages, name="api_messages"),
    path("api/messages/audience/", inbox.api_message_audience, name="api_message_audience"),
    path("api/messages/audience-preview/", inbox.api_message_audience_preview, name="api_message_audience_preview"),
    path("api/messages/<int:pk>/", inbox.api_message_detail, name="api_message_detail"),
    path("api/messages/<int:pk>/send/", inbox.api_message_send, name="api_message_send"),
    path("api/messages/<int:pk>/recipients/", inbox.api_message_recipients, name="api_message_recipients"),

    # --- Knockout bracket: everyone reads, admins PATCH ---
    path("api/bracket/", views_bracket.api_bracket, name="api_bracket"),
]
