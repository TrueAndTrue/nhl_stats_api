from django.urls import path

from . import views

urlpatterns = [
  path("query_all_games/", views.query_all_games, name="query_all_games"),
  path("", views.index, name="index")
]