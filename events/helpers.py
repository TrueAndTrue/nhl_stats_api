from events.models import Goal, Shot, Hit, Faceoff, Penalty, MissedShot, BlockedShot, Giveaway
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse

class JsonEncoder(DjangoJSONEncoder):
    def default(self, obj):
        return {'nhl_api_id': obj.nhl_api_id }

def faceoff_handler(faceoff_data, game_id, season_type):
  faceoff = Faceoff.objects.create(
    winner = faceoff_data["details"]["winningPlayerId"],
    loser = faceoff_data["details"]["losingPlayerId"],
    period = faceoff_data["period"],
    period_time = faceoff_data["timeInPeriod"],
    season_type = season_type,
    coord_x = faceoff_data["details"]["xCoord"],
    coord_y = faceoff_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(faceoff)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def hit_handler(hit_data, game_id, season_type):
  hit = Hit.objects.create(
    hitter = hit_data["details"]["hittingPlayerId"],
    hittee = hit_data["details"]["hitteePlayerId"],
    period = hit_data["period"],
    period_time = hit_data["timeInPeriod"],
    season_type = season_type,
    coord_x = hit_data["details"]["xCoord"],
    coord_y = hit_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(hit)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def goal_handler(goal_data, game_id, season_type):
  goal = Goal.objects.create(
    scorer = goal_data["details"]["scoringPlayerId"],
    assist = goal_data["details"]["assist1PlayerId"],
    assist2 = goal_data["details"]["assist2PlayerId"],
    goalie = goal_data["details"]["goalieInNetId"],
    shot_type = goal_data["details"]["shotType"],
    period = goal_data["period"],
    period_time = goal_data["timeInPeriod"],
    season_type = season_type,
    coord_x = goal_data["details"]["xCoord"],
    coord_y = goal_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(goal)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def shot_handler(shot_data, game_id, season_type):
  shot = Shot.objects.create(
    shooter = shot_data["details"]["shootingPlayerId"],
    goalie = shot_data["details"]["goalieInNetId"],
    shot_type = shot_data["details"]["shotType"],
    period = shot_data["period"],
    period_time = shot_data["timeInPeriod"],
    season_type = season_type,
    coord_x = shot_data["details"]["xCoord"],
    coord_y = shot_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(shot)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def giveaway_handler(giveaway_data, game_id, season_type):
  giveaway = Giveaway.objects.create(
    player = giveaway_data["details"]["playerId"],
    period = giveaway_data["period"],
    period_time = giveaway_data["timeInPeriod"],
    season_type = season_type,
    coord_x = giveaway_data["details"]["xCoord"],
    coord_y = giveaway_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(giveaway)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def missed_shot_handler(missed_shot_data, game_id, season_type):
  missed_shot = MissedShot.objects.create(
    shooter = missed_shot_data["details"]["shootingPlayerId"],
    goalie = missed_shot_data["details"]["goalieInNetId"],
    shot_type = missed_shot_data["details"]["shotType"],
    reason = missed_shot_data["details"]["reason"],
    period = missed_shot_data["period"],
    period_time = missed_shot_data["timeInPeriod"],
    season_type = season_type,
    coord_x = missed_shot_data["details"]["xCoord"],
    coord_y = missed_shot_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(missed_shot)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def blocked_shot_handler(blocked_shot_data, game_id, season_type):
  blocked_shot = BlockedShot.objects.create(
    blocker = blocked_shot_data["details"]["blockingPlayerId"],
    shooter = blocked_shot_data["details"]["shootingPlayerId"],
    period = blocked_shot_data["period"],
    period_time = blocked_shot_data["timeInPeriod"],
    season_type = season_type,
    coord_x = blocked_shot_data["details"]["xCoord"],
    coord_y = blocked_shot_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(blocked_shot)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

def penalty_handler(penalty_data, game_id, season_type):
  penalty = Penalty.objects.create(
    penalty_on = penalty_data["details"]["committedByPlayerId"],
    drew_by = penalty_data["details"]["drawnByPlayerId"],
    penalty_type = penalty_data["details"]["descKey"],
    minutes = penalty_data["details"]["duration"],
    period = penalty_data["period"],
    period_time = penalty_data["timeInPeriod"],
    season_type = season_type,
    coord_x = penalty_data["details"]["xCoord"],
    coord_y = penalty_data["details"]["yCoord"],
    game_id = game_id
  )
  json_data = JsonEncoder().encode(penalty)
  print(json_data, "JSON DATA")
  return JsonResponse({'event_data': json_data}, safe=False)

