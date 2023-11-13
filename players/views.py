from django.http import JsonResponse, HttpResponse
from players.models import Player
from django.core.serializers.json import DjangoJSONEncoder
import requests
from django.forms.models import model_to_dict
from events.models import Goal, Shot, Hit, Faceoff, Penalty, MissedShot, BlockedShot, Giveaway

def index(request):
  players = Player.objects.all()
  print(players, "PLAYERS")
  return HttpResponse(players)

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
  names = name.split(" ")

  if len(names) == 1:
    first_name = names[0]
    
    try:
      players = Player.objects.filter(first_name__startswith=first_name)
      player_dicts = [model_to_dict(player) for player in players]
      sorted_player_list = sorted(player_dicts, key=player_sort_key)
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
    return JsonResponse({"amount": len(sorted_player_list),"players": list(sorted_player_list)}, safe=False)
  except Player.DoesNotExist:
    players2 = None

  return players2