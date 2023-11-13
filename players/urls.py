from django.urls import path

from . import views

urlpatterns = [
  path("find-players-by-name/", views.find_players_by_name, name="find-players-by-name"),
  path("find-player", views.find_player, name="find_player"),
  path("faceoff-player-finder", views.faceoff_player_finder, name="faceoff_player_finder"),
  path("blocked-shot-player-finder", views.blocked_shot_player_finder, name="blocked_shot_player_finder"),
  path("penalty-player-finder", views.penalty_player_finder, name="penalty_player_finder"),
  path("missed-shot-player-finder", views.missed_shot_player_finder, name="missed_shot_player_finder"),
  path("goal-player-finder", views.goal_player_finder, name="goal_player_finder"),
  path("giveaway-player-finder", views.giveaway_player_finder, name="giveaway_player_finder"),
  path("shot-player-finder", views.shot_player_finder, name="shot_player_finder"),
  path("hit-player-finder", views.hit_player_finder, name="hit_player_finder"),
  path("", views.index, name="index"),
]