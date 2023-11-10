from django.db import models
import uuid

# make names snake case
class Goal(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  description = models.CharField(max_length=255)
  shot_type = models.CharField(max_length=255)
  strength = models.CharField(max_length=255)
  empty_net = models.BooleanField()
  game_winning_goal = models.BooleanField()
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
  description = models.CharField(max_length=255)
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
  description = models.CharField(max_length=255)
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
  description = models.CharField(max_length=255)
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
  description = models.CharField(max_length=255)
  player = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Penalty(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  description = models.CharField(max_length=255)
  penalty_on = models.CharField(max_length=255)
  drew_by = models.CharField(max_length=255)
  penalty_type = models.CharField(max_length=255)
  minutes = models.IntegerField()
  severity = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class BlockedShot(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  description = models.CharField(max_length=255)
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
  description = models.CharField(max_length=255)
  shooter = models.CharField(max_length=255)
  goalie = models.CharField(max_length=255)
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Stop(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  description = models.CharField(max_length=255)
  goalie = models.CharField(max_length=255) # do i have this info
  shooter = models.CharField(max_length=255) # do i have this info
  shot_type = models.CharField(max_length=255) # do i have this info
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  coord_x = models.IntegerField()
  coord_y = models.IntegerField()
  game_id = models.IntegerField()

class Challenge(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # make this generated
  description = models.CharField(max_length=255)
  team = models.CharField(max_length=255) # ???
  period = models.IntegerField()
  period_time = models.TimeField()
  season_type = models.CharField(max_length=255)
  game_id = models.IntegerField()