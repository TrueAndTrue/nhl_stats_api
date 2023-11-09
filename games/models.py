from django.db import models

class Games(models.Model):
  id = models.IntegerField(primary_key=True)
  season = models.CharField(max_length=8)
  game_date = models.DateField()
  game_start = models.TimeField()
  game_end = models.TimeField()
  winner = models.CharField(max_length=3)
  loser = models.CharField(max_length=3)
  home_team = models.CharField(max_length=3)
  away_team = models.CharField(max_length=3)
  home_goals = models.IntegerField()
  away_goals = models.IntegerField()
  gameId = models.IntegerField()

