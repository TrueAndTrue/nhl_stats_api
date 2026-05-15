from django.urls import path

from . import views

urlpatterns = [
    path("landing/", views.landing, name="api-landing"),
    path("players/", views.player_directory, name="api-players"),
    path("players/search/", views.player_search, name="api-player-search"),
    path("players/<int:player_id>/", views.player_profile, name="api-player"),
    path("comparison/", views.comparison, name="api-comparison"),
    path("versus/", views.versus, name="api-versus"),
    path("records/", views.records, name="api-records"),
    path("records/overview/", views.records_overview, name="api-records-overview"),
    path("games/", views.games_directory, name="api-games"),
    path("games/<int:game_id>/", views.game_center, name="api-game"),
    path("rink-lab/", views.rink_lab, name="api-rink-lab"),
    path("rink-lab/bin/", views.rink_bin, name="api-rink-bin"),
    path("eras/", views.eras, name="api-eras"),
]
