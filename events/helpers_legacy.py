from events.models import Goal, Shot, Hit, Faceoff, Penalty, MissedShot, BlockedShot, Giveaway
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from datetime import datetime, time


class BaseHandler:
    model_class = None

    def __init__(self, data, game_id, season_type):
        self.data = data
        self.game_id = game_id
        self.season_type = season_type

    def create_event(self):
        
        for letter in self.data["timeInPeriod"]:
          if letter.isalpha():
            self.data["timeInPeriod"] = "00:00"    
        minutesTime = int(self.data["timeInPeriod"].split(":")[0])
        secondsTime = int(self.data["timeInPeriod"].split(":")[1])
        if minutesTime > 20:
          self.data["timeInPeriod"] = "00:00"
        elif secondsTime > 60:
          self.data["timeInPeriod"] = "00:00"
        time_in_period = datetime.strptime(self.data.get("timeInPeriod"), "%H:%M").time() if self.data.get("timeInPeriod") else None
        
        print(str(self.game_id) + str(self.data["eventId"]))
        
        try:
          data_existing = self.model_class.objects.get(event_id=str(self.game_id) + str(self.data["eventId"]))
        except self.model_class.DoesNotExist:
          data_existing = None
        if data_existing:
          print('dup')
          return JsonResponse({'event_data': {}}, safe=False)

        additional_fields = self.get_additional_fields()
        event_instance = self.model_class.objects.create(
            period=self.data.get("period"),
            period_time=time_in_period,
            season_type=self.season_type,
            coord_x=self.data["details"].get("xCoord"),
            coord_y=self.data["details"].get("yCoord"),
            game_id=self.game_id,
            event_id = str(self.game_id) + str(self.data["eventId"]),
            **additional_fields
        )
        json_data = JsonEncoder().encode(event_instance)
        return JsonResponse({'event_data': json_data}, safe=False)

    def get_additional_fields(self):
        raise NotImplementedError("Subclasses must implement this method.")


class JsonEncoder(DjangoJSONEncoder):
    def default(self, obj):
        return {'game_id': obj.game_id }

class FaceoffHandler(BaseHandler):

  model_class = Faceoff

  def get_additional_fields(self):
    return {
      'winner': self.data["details"].get("winningPlayerId"),
      'loser': self.data["details"].get("losingPlayerId"),
    }

class HitHandler(BaseHandler):
  
  model_class = Hit

  def get_additional_fields(self):
    return {
      'hitter': self.data["details"].get("hittingPlayerId"),
      'hittee': self.data["details"].get("hitteePlayerId"),
    }


class GoalHandler(BaseHandler):

  model_class = Goal

  def get_additional_fields(self):
    return {
      'scorer': self.data["details"].get("scoringPlayerId"),
      'assist': self.data["details"].get("assist1PlayerId"),
      'assist2': self.data["details"].get("assist2PlayerId"),
      'goalie': self.data["details"].get("goalieInNetId"),
      'shot_type': self.data["details"].get("shotType"),
    }

class ShotHandler(BaseHandler):

  model_class = Shot

  def get_additional_fields(self):
    return {
      'shooter': self.data["details"].get("shootingPlayerId"),
      'goalie': self.data["details"].get("goalieInNetId"),
      'shot_type': self.data["details"].get("shotType"),
    }

class GiveawayHandler(BaseHandler):

  model_class = Giveaway

  def get_additional_fields(self):
    return {
      'player': self.data["details"].get("playerId"),
    }

class MissedShotHandler(BaseHandler):

  model_class = MissedShot

  def get_additional_fields(self):
    return {
      'shooter': self.data["details"].get("shootingPlayerId"),
      'goalie': self.data["details"].get("goalieInNetId"),
      'reason': self.data["details"].get("reason"),
    }

class BlockedShotHandler(BaseHandler):

  model_class = BlockedShot

  def get_additional_fields(self):
    return {
      'blocker': self.data["details"].get("blockingPlayerId"),
      'shooter': self.data["details"].get("shootingPlayerId"),
    }

class PenaltyHandler(BaseHandler):

  model_class = Penalty

  def get_additional_fields(self):
    return {
      'penalty_on': self.data["details"].get("committedByPlayerId"),
      'drew_by': self.data["details"].get("drawnByPlayerId"),
      'penalty_type': self.data["details"].get("descKey"),
      'minutes': self.data["details"].get("duration"),
    }

def handle_event(event_type, data, game_id, season_type):
    handler_classes = {
        "faceoff": FaceoffHandler,
        "hit": HitHandler,
        "goal": GoalHandler,
        "shot-on-goal": ShotHandler,
        "giveaway": GiveawayHandler,
        "missed-shot": MissedShotHandler,
        "blocked-shot": BlockedShotHandler,
        "penalty": PenaltyHandler,
    }

    handler_class = handler_classes.get(event_type)
    if handler_class:
        handler = handler_class(data, game_id, season_type)
        return handler.create_event()
    else:
        return JsonResponse({'error': 'Invalid event type'}, status=400)