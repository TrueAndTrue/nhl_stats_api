from django.shortcuts import HttpResponse
from players.models import Player
import requests

def index(request):
  players = Player.objects.all()
  print(players, "PLAYERS")
  return HttpResponse(players)

def create_player(player_id):
  print("request to create player" + player_id)
  base_url = "https://api-web.nhle.com/v1/player/"
  url = base_url + player_id + "/landing"
  response = requests.get(url)
  player = response.json()
  print(player, "PLAYER")
  return HttpResponse(player)