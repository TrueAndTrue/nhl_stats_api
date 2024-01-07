from django.http import JsonResponse, HttpResponse
from players.models import Player
from django.core.serializers.json import DjangoJSONEncoder
import requests
from django.forms.models import model_to_dict
from events.models import Goal, Shot, Hit, Faceoff, Penalty, MissedShot, BlockedShot, Giveaway

def index(request):
  print(request.body)
  return HttpResponse(request.body)

class PlayerEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Player):
            return {'nhl_api_id': obj.nhl_api_id }
        return super().default(obj)

class LargeObject:
    def __init__(self, **kwargs):
        self.nhl_api_id = kwargs.get('playerId', -1)
        first_name = kwargs.get('firstName', {})
        self.first_name = first_name.get('default', 'Default First Name')
        last_name = kwargs.get('lastName', {})
        self.last_name = last_name.get('default', 'Default Last Name')
        self.is_active = kwargs.get('isActive', False)
        self.jersey_number = kwargs.get('sweaterNumber', -1)
        self.primary_position = kwargs.get('position', 'Default Position')
        self.headshot = kwargs.get('headshot', 'Default Headshot URL')
        self.hero_image = kwargs.get('heroImage', 'Default Hero Image URL')
        self.birth_date = kwargs.get('birthDate', 'Default Birth Date')
        self.height_in_cm = kwargs.get('heightInCentimeters', -1)
        self.weight_in_lbs = kwargs.get('weightInPounds', -1)

def create_player(player_id):
  try:
    player_existing = Player.objects.get(nhl_api_id=player_id)
  except Player.DoesNotExist:
    player_existing = None
  if player_existing:
    json_data = PlayerEncoder().encode(player_existing)
    return JsonResponse({'player_data': json_data}, safe=False)
  base_url = "https://api-web.nhle.com/v1/player/"
  url = base_url + str(player_id)+ "/landing"
  try:
    response = requests.get(url)
    if response.status_code == 404:
      return JsonResponse({'player_data': None}, safe=False)
  except:
    print("ERROR")
  player = response.json()
  player_existing = None
  curated_player = LargeObject(**player)
  created_player = Player.objects.create(
    nhl_api_id = curated_player.nhl_api_id,
    first_name = curated_player.first_name,
    last_name = curated_player.last_name,
    is_active = curated_player.is_active,
    jersey_number = curated_player.jersey_number,
    primary_position = curated_player.primary_position,
    headshot = curated_player.headshot,
    hero_image = curated_player.hero_image,
    birth_date = curated_player.birth_date,
    height_in_cm = curated_player.height_in_cm,
    weight_in_lbs = curated_player.weight_in_lbs
  )
  json_data = PlayerEncoder().encode(created_player)
  return JsonResponse({'player_data': json_data}, safe=False)

def sort_key(data, key='game_id'):
    return str(data[key])[:4]

def find_player(request):
  player_id = request.GET.get('playerId')
  try:
    player = Player.objects.get(nhl_api_id=player_id)
  except Player.DoesNotExist:
    player = None
  if player:
    print(player)
    player_dict = model_to_dict(player)
    return JsonResponse({'player_data': player_dict}, safe=False)
  else:
    return JsonResponse({'player_data': None}, safe=False)
  
def player_comparison_goal_handler(goalList):

  if (len(goalList) == 0):
    return {"most_common_shot_type": None, "goal_count": 0, "most_common_period": None}
  goal_shot_type_map = {}
  goal_period_map = {}
  goal_count = 0
  
  for goal in goalList:
    goal_shot_type_map[goal["shot_type"]] = goal_shot_type_map.get(goal["shot_type"], 0) + 1
    goal_period_map[goal["period"]] = goal_period_map.get(goal["period"], 0) + 1
    goal_count += 1

  sorted_shot_type_dict = dict(sorted(goal_shot_type_map.items(), key=lambda item: item[1], reverse=True))
  sorted_period_dict = dict(sorted(goal_period_map.items(), key=lambda item: item[1], reverse=True))


  print(goal_shot_type_map)
  print(goal_period_map)
  print(goal_count)


  most_common_shot_type = list(sorted_shot_type_dict.keys())[0]
  for key in sorted_shot_type_dict.keys():
    if key != None:
      most_common_shot_type = key
      break
  most_common_period = list(sorted_period_dict.keys())[0]

  return {"most_common_shot_type": most_common_shot_type, "goal_count": goal_count, "most_common_period": most_common_period}

def player_comparison(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player1 or not player2:
    return JsonResponse({"data": []}, safe=False)
  
  player_1_goals = player_comparison_goal_handler(list(Goal.objects.filter(scorer=player1).values()))
  print(player_1_goals)
  player_1_hits = len(list(Hit.objects.filter(hitter=player1).values()))
  player_1_hittees = len(list(Hit.objects.filter(hittee=player1).values()))
  player_1_faceoff_wins = len(list(Faceoff.objects.filter(winner=player1).values()))
  player_1_faceoff_losses = len(list(Faceoff.objects.filter(loser=player1).values()))
  player_1_shots = len(list(Shot.objects.filter(shooter=player1).values()))
  player_1_penalties = len(list(Penalty.objects.filter(penalty_on=player1).values()))
  player_1_penalties_drawn = len(list(Penalty.objects.filter(drew_by=player1).values()))
  player_1_missed_shots = len(list(MissedShot.objects.filter(shooter=player1).values()))
  player_1_blocked_shots = len(list(BlockedShot.objects.filter(blocker=player1).values()))
  player_1_giveaways = len(list(Giveaway.objects.filter(player=player1).values()))
  
  player_2_goals = player_comparison_goal_handler(list(Goal.objects.filter(scorer=player2).values()))
  player_2_hits = len(list(Hit.objects.filter(hitter=player2).values()))
  player_2_hittees = len(list(Hit.objects.filter(hittee=player2).values()))
  player_2_faceoff_wins = len(list(Faceoff.objects.filter(winner=player2).values()))
  player_2_faceoff_losses = len(list(Faceoff.objects.filter(loser=player2).values()))
  player_2_shots = len(list(Shot.objects.filter(shooter=player2).values()))
  player_2_penalties = len(list(Penalty.objects.filter(penalty_on=player2).values()))
  player_2_penalties_drawn = len(list(Penalty.objects.filter(drew_by=player2).values()))
  player_2_missed_shots = len(list(MissedShot.objects.filter(shooter=player2).values()))
  player_2_blocked_shots = len(list(BlockedShot.objects.filter(blocker=player2).values()))
  player_2_giveaways = len(list(Giveaway.objects.filter(player=player2).values()))

  player1Stats = {
    "goal_count": player_1_goals["goal_count"],
    "most_common_shot_type": player_1_goals["most_common_shot_type"],
    "most_common_period": player_1_goals["most_common_period"],
    "hits": player_1_hits,
    "hittees": player_1_hittees,
    "faceoff_wins": player_1_faceoff_wins,
    "faceoff_losses": player_1_faceoff_losses,
    "shots": player_1_shots,
    "penalties": player_1_penalties,
    "penalties_drawn": player_1_penalties_drawn,
    "missed_shots": player_1_missed_shots,
    "blocked_shots": player_1_blocked_shots,
    "giveaways": player_1_giveaways
  }

  player2Stats = {
    "goal_count": player_2_goals["goal_count"],
    "most_common_shot_type": player_2_goals["most_common_shot_type"],
    "most_common_period": player_2_goals["most_common_period"],
    "hits": player_2_hits,
    "hittees": player_2_hittees,
    "faceoff_wins": player_2_faceoff_wins,
    "faceoff_losses": player_2_faceoff_losses,
    "shots": player_2_shots,
    "penalties": player_2_penalties,
    "penalties_drawn": player_2_penalties_drawn,
    "missed_shots": player_2_missed_shots,
    "blocked_shots": player_2_blocked_shots,
    "giveaways": player_2_giveaways
  }

  return JsonResponse({"player1": player1Stats, "player2": player2Stats}, safe=False)

def player_comparison_goalie(request): 
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player1 or not player2:
    return JsonResponse({"data": []}, safe=False)
  
  player_1_goals_allowed = len(list(Goal.objects.filter(goalie=player1).values()))
  player_1_shots_against = len(list(Shot.objects.filter(goalie=player1).values()))
  player_1_save_percentage = round(1 - (player_1_goals_allowed / player_1_shots_against), 3)
  player_1_penalties = len(list(Penalty.objects.filter(penalty_on=player1).values()))
  player_1_penalties_drawn = len(list(Penalty.objects.filter(drew_by=player1).values()))

  player_2_goals_allowed = len(list(Goal.objects.filter(goalie=player2).values()))
  player_2_shots_against = len(list(Shot.objects.filter(goalie=player2).values()))
  player_2_save_percentage = round(1 - (player_2_goals_allowed / player_2_shots_against), 3)
  player_2_penalties = len(list(Penalty.objects.filter(penalty_on=player2).values()))
  player_2_penalties_drawn = len(list(Penalty.objects.filter(drew_by=player2).values()))


  player1Stats = {
    "goals_allowed": player_1_goals_allowed,
    "shots_against": player_1_shots_against,
    "save_percentage": player_1_save_percentage,
    "penalties": player_1_penalties,
    "penalties_drawn": player_1_penalties_drawn
  }

  player2Stats = {
    "goals_allowed": player_2_goals_allowed,
    "shots_against": player_2_shots_against,
    "save_percentage": player_2_save_percentage,
    "penalties": player_2_penalties,
    "penalties_drawn": player_2_penalties_drawn
  }

  return JsonResponse({"player1": player1Stats, "player2": player2Stats}, safe=False)

def player_versus_player(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player1 or not player2:
    return JsonResponse({"data": []}, safe=False)
  
  hits = len(list(Hit.objects.filter(hitter=player1, hittee=player2).values()))
  faceoff_wins = len(list(Faceoff.objects.filter(winner=player1, loser=player2).values()))
  penalties = len(list(Penalty.objects.filter(penalty_on=player1, drew_by=player2).values()))
  blocked_shots = len(list(BlockedShot.objects.filter(blocker=player1, shooter=player2).values()))

  return JsonResponse({"hits": hits, "faceoff_wins": faceoff_wins, "penalties": penalties, "blocked_shots": blocked_shots}, safe=False)

def player_versus_goalie(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player1 or not player2:
    return JsonResponse({"data": []}, safe=False)
  
  goal_object = player_comparison_goal_handler(list(Goal.objects.filter(scorer=player1).values()))
  shots = len(list(Shot.objects.filter(shooter=player1, goalie=player2).values()))
  score_percentage = round(goal_object["goal_count"] / shots, 3)
  penalties = len(list(Penalty.objects.filter(penalty_on=player1, drew_by=player2).values()))
  missed_shots = len(list(MissedShot.objects.filter(shooter=player1, goalie=player2).values()))

  return JsonResponse({"goals": goal_object["goal_count"], "shots": shots, "score_percentage": score_percentage, "most_common_shot_type": goal_object["most_common_shot_type"], "missed_shots": missed_shots, "penalties": penalties}, safe=False)


def hit_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = Hit.objects.filter(hitter=player1)

  else: 
    data = Hit.objects.filter(hitter=player1, hittee=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def faceoff_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = Faceoff.objects.filter(winner=player1)

  else: 
    data = Faceoff.objects.filter(winner=player1, loser=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def shot_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = Shot.objects.filter(shooter=player1)

  else: 
    data = Shot.objects.filter(shooter=player1, goalie=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def goal_player_finder(player1, player2):
  data = Goal.objects.filter(scorer=player1, goalie=player2)
  print(data)
  return data

def penalty_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = Penalty.objects.filter(penalty_on=player1)

  else: 
    data = Penalty.objects.filter(penalty_on=player1, drew_by=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def missed_shot_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = MissedShot.objects.filter(shooter=player1)

  else: 
    data = MissedShot.objects.filter(shooter=player1, goalie=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def blocked_shot_player_finder(request):
  player1 = request.GET.get('player1')
  player2 = request.GET.get('player2')

  if not player2:
    data = BlockedShot.objects.filter(blocker=player1)

  else: 
    data = BlockedShot.objects.filter(blocker=player1, shooter=player2)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def giveaway_player_finder(request):
  player = request.GET.get('player')

  data = Giveaway.objects.filter(player=player)
    
  data_list = list(data.values())
  if len(data_list) == 0:
    return JsonResponse({"data": []}, safe=False)
  sorted_data_list = sorted(data_list, key=sort_key)
  oldest_game = str(sorted_data_list[0]['game_id'])[:4]
  newest_game = str(sorted_data_list[-1]['game_id'])[:4]
  return JsonResponse({"oldestGame": oldest_game, "newestGame": newest_game, "amount": len(sorted_data_list),"data": sorted_data_list}, safe=False)

def player_sort_key(data, key='last_name'):
    return str(data[key])

def find_players_by_name(request):
  name = request.GET.get('name')
  if (not name):
    return JsonResponse({"amount": 0, "players": []}, safe=False)
  names = name.split(" ")

  for i in range(len(names)):
    names[i] = names[i][0].upper() + names[i][1:].lower()

  if len(names) == 1:
    first_name = names[0]
    
    try:
      players = Player.objects.filter(first_name__startswith=first_name)
      player_dicts = [model_to_dict(player) for player in players]
      sorted_player_list = sorted(player_dicts, key=player_sort_key)
      if len(sorted_player_list) < 5:
        players_by_last = Player.objects.filter(last_name__startswith=first_name)
        player_dicts_by_last = [model_to_dict(player) for player in players_by_last]
        sorted_player_list_by_last = sorted(player_dicts_by_last, key=player_sort_key)
        return JsonResponse({"amount": len(sorted_player_list + sorted_player_list_by_last),"players": list(sorted_player_list + sorted_player_list_by_last)}, safe=False)
      return JsonResponse({"amount": len(sorted_player_list), "players": list(sorted_player_list)}, safe=False)
    except Player.DoesNotExist:
      players = None
  else:
    first_name = names[0]
    last_name = names[1]
  try:
    players = Player.objects.filter(first_name__startswith=first_name)
    players2 = players.filter(last_name__startswith=last_name)
    player_dicts = [model_to_dict(player) for player in players2]
    sorted_player_list = sorted(player_dicts, key=player_sort_key)
    if len(sorted_player_list) < 5:
      players_by_last = Player.objects.filter(last_name__startswith=first_name)
      players_by_last_2 = players_by_last.filter(first_name__startswith=last_name)
      player_dicts_by_last = [model_to_dict(player) for player in players_by_last_2]
      sorted_player_list_by_last = sorted(player_dicts_by_last, key=player_sort_key)
      return JsonResponse({"amount": len(sorted_player_list + sorted_player_list_by_last),"players": list(sorted_player_list + sorted_player_list_by_last)}, safe=False)
    return JsonResponse({"amount": len(sorted_player_list),"players": list(sorted_player_list)}, safe=False)
  except Player.DoesNotExist:
    players2 = None

  return players2