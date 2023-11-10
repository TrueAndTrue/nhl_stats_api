from django.db import models
import uuid

class Player(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  nhl_api_id = models.IntegerField()
  first_name = models.CharField(max_length=255)
  last_name = models.CharField(max_length=255)
  is_active = models.BooleanField()
  jersey_number = models.IntegerField()
  primary_position = models.CharField(max_length=255)
  headshot = models.CharField(max_length=255)
  hero_image = models.CharField(max_length=255)
  birth_date = models.DateField()
  height_in_cm = models.IntegerField()
  weight_in_lbs = models.IntegerField()