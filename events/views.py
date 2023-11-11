from django.http import HttpResponse, HttpRequest, JsonResponse
import requests
from players.views import create_player
from events.helpers import faceoff_handler, hit_handler, goal_handler, shot_handler, giveaway_handler, missed_shot_handler, blocked_shot_handler, penalty_handler

def index(request):
  return HttpResponse("Hello, world. You're at the events index.")

def query_all_games(request):

  # VARS
  QUERY_TYPE = "event"  # player / event / game
  FIRST_SEASON = 1917
  LAST_SEASON = 2023
  REGULAR_SEASON = 2
  PLAYOFFS = 3
  base_url = 'https://api-web.nhle.com/v1/gamecenter/' # the number is what we're changing
  response = requests.get(base_url)
  season = FIRST_SEASON

  # LOGIC
  while season <= LAST_SEASON:
    print(season, "SEASON")
    game_type = REGULAR_SEASON
    while game_type <= PLAYOFFS:
      game_number = 1

      # PLAYOFF LOGIC
      if game_type == PLAYOFFS:
        playoff_games = playoff_game_number_generator()
        for game in playoff_games:
          url = base_url + str(season) + "0" + str(game_type) + game + "/play-by-play"
          try:
            response = requests.get(url)
          except:
            continue
          if response.status_code == 404:
            continue
          game_data = response.json()
          if QUERY_TYPE == "player":
            for player in game_data["rosterSpots"]:
              create_player(player["playerId"])

      # REGULAR SEASON LOGIC
      while game_number <= 1353:
        print(game_number)
        game_id = str(season) + "0" + str(game_type) + game_number_formatter(game_number)
        url = base_url + game_id + "/play-by-play"
        try:
          response = requests.get(url)
        except:
          continue
        if response.status_code == 404:
          game_number = 1
          break
        game_data = response.json()

        # Conditional Logic
        if QUERY_TYPE == "player":
          for player in game_data["rosterSpots"]:
            create_player(player["playerId"])

        elif QUERY_TYPE == "event":
          for play in game_data["plays"]:
            if play["typeDescKey"] == "faceoff":
              faceoff_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "hit":
              hit_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "shot-on-goal":
              shot_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "giveaway":
              giveaway_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "missed-shot":
              missed_shot_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "blocked-shot":
              blocked_shot_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "penalty":
              penalty_handler(play, game_id, "regular")
            elif play["typeDescKey"] == "goal":
              goal_handler(play, game_id, "regular")
            else:
              continue
        game_number += 1
      game_type += 1
    season += 1
  return JsonResponse({ 'message': "successful!"}, safe=False)
  

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