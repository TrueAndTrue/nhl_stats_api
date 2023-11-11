from django.db import models
import uuid

# make names snake case
class Goal(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  shot_type = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  scorer = models.CharField(max_length=255)
  assist = models.CharField(max_length=255)
  assist2 = models.CharField(max_length=255)
  goalie = models.CharField(max_length=255)
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Hit(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  hitter = models.CharField(max_length=255)
  hittee = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Faceoff(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  winner = models.CharField(max_length=255)
  loser = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Shot(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  shooter = models.CharField(max_length=255)
  goalie = models.CharField(max_length=255)
  shot_type = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Giveaway(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  player = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Penalty(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  penalty_on = models.CharField(max_length=255)
  drew_by = models.CharField(max_length=255)
  penalty_type = models.CharField(max_length=255)
  minutes = models.IntegerField()
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class BlockedShot(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  blocker = models.CharField(max_length=255)
  shooter = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class MissedShot(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  shooter = models.CharField(max_length=255)
  goalie = models.CharField(max_length=255)
  reason = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()