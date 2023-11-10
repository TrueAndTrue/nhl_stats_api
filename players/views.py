from django.http import JsonResponse, HttpResponse
from players.models import Player
from django.core.serializers.json import DjangoJSONEncoder
import requests

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
        self.jersey_number = kwargs.get('jerseyNumber', -1)
        self.primary_position = kwargs.get('position', 'Default Position')
        self.headshot = kwargs.get('headshot', 'Default Headshot URL')
        self.hero_image = kwargs.get('heroImage', 'Default Hero Image URL')
        self.birth_date = kwargs.get('birthDate', 'Default Birth Date')
        self.height_in_cm = kwargs.get('heightInCentimeters', -1)
        self.weight_in_lbs = kwargs.get('weightInPounds', -1)

def create_player(player_id):
  print("request to create player" + str(player_id))
  base_url = "https://api-web.nhle.com/v1/player/"
  url = base_url + str(player_id)+ "/landing"
  response = requests.get(url)
  player = response.json()
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