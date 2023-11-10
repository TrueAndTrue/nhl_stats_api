from django.http import HttpResponse, HttpRequest, JsonResponse
from events.models import Goal, Shot, Hit, Faceoff, Penalty, MissedShot, BlockedShot, Giveaway, Stop, Challenge
import requests

def index(request):
  return HttpResponse("Hello, world. You're at the events index.")

def query_all_games(request):
  base_url = 'https://api-web.nhle.com/v1/gamecenter/' # the number is what we're changing
  response = requests.get(base_url)
  FIRST_SEASON = 1917
  LAST_SEASON = 1918
  season = FIRST_SEASON
  REGULAR_SEASON = 2
  PLAYOFFS = 3
  games = []
  while season <= LAST_SEASON:
    game_type = REGULAR_SEASON
    while game_type <= PLAYOFFS:
      game_number = 1
      if game_type == PLAYOFFS:
        playoff_games = playoff_game_number_generator()
        for game in playoff_games:
          url = base_url + str(season) + "0" + str(game_type) + game + "/play-by-play"
          response = requests.get(url)
          if response.status_code == 404:
            continue
          games.append(response.json())

      while game_number <= 1353:
        url = base_url + str(season) + "0" + str(game_type) + game_number_formatter(game_number) + "/play-by-play"
        response = requests.get(url)
        if response.status_code == 404:
          game_number = 1
          break
        games.append(response.json())
        game_number += 1
      game_type += 1
    season += 1
  return JsonResponse(games, safe=False)
  

def game_number_formatter(game_number):
  if game_number < 10:
    return "000" + str(game_number)
  elif game_number < 100:
    return "00" + str(game_number)
  elif game_number < 1000:
    return "0" + str(game_number)
  else:
    return str(game_number)
  
def playoff_game_number_generator():
  MAX_ROUND = 4
  matchup = 1
  round = 1
  game_strs = []
  while round <= MAX_ROUND:
    matchup = 1
    if round == 1:
      while matchup <= 8:
        game = 1
        while game <= 7:
          game_strs.append("0" + str(round) + str(matchup) + str(game))
          game += 1
        matchup += 1

    elif round == 2:
      while matchup <= 4:
        game = 1
        while game <= 7:
          game_strs.append("0" + str(round) + str(matchup) + str(game))
          game += 1
        matchup += 1

    elif round == 3:
      while matchup <= 2:
        game = 1
        while game <= 7:
          game_strs.append("0" + str(round) + str(matchup) + str(game))
          game += 1
        matchup += 1

    elif round == 4:
      game = 1
      while game <= 7:
        game_strs.append("0" + str(round) + "1" + str(game))
        game += 1
    round += 1
  return game_strs