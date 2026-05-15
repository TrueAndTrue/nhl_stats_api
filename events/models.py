from django.db import models

from games.models import Game
from players.models import Player


class Event(models.Model):
    """
    A single play-by-play event. The `type_desc` discriminator decides what
    the player FK roles mean — see the role table:

        | type_desc      | primary_player | secondary_player | tertiary_player | goalie         |
        |----------------|----------------|------------------|-----------------|----------------|
        | goal           | scorer         | assist1          | assist2         | goalie_against |
        | shot-on-goal   | shooter        |                  |                 | goalie_against |
        | hit            | hitter         | hittee           |                 |                |
        | faceoff        | winner         | loser            |                 |                |
        | giveaway       | player         |                  |                 |                |
        | takeaway       | player         |                  |                 |                |
        | penalty        | committed_by   | drawn_by         | served_by       |                |
        | blocked-shot   | blocker        | shooter          |                 |                |
        | missed-shot    | shooter        |                  |                 | goalie_against |
    """

    GOAL = "goal"
    SHOT_ON_GOAL = "shot-on-goal"
    HIT = "hit"
    FACEOFF = "faceoff"
    GIVEAWAY = "giveaway"
    TAKEAWAY = "takeaway"
    PENALTY = "penalty"
    BLOCKED_SHOT = "blocked-shot"
    MISSED_SHOT = "missed-shot"

    TYPE_CHOICES = [
        (GOAL, "Goal"),
        (SHOT_ON_GOAL, "Shot on Goal"),
        (HIT, "Hit"),
        (FACEOFF, "Faceoff"),
        (GIVEAWAY, "Giveaway"),
        (TAKEAWAY, "Takeaway"),
        (PENALTY, "Penalty"),
        (BLOCKED_SHOT, "Blocked Shot"),
        (MISSED_SHOT, "Missed Shot"),
    ]

    id = models.BigAutoField(primary_key=True)
    nhl_event_id = models.CharField(max_length=64, unique=True)

    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name="events"
    )
    type_desc = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)
    type_code = models.IntegerField(null=True, blank=True)

    period = models.IntegerField(null=True, blank=True)
    period_time = models.TimeField(null=True, blank=True)
    period_type = models.CharField(
        max_length=8, null=True, blank=True
    )  # REG, OT, SO

    coord_x = models.IntegerField(null=True, blank=True)
    coord_y = models.IntegerField(null=True, blank=True)
    zone_code = models.CharField(max_length=1, null=True, blank=True)
    situation_code = models.CharField(max_length=4, null=True, blank=True)

    primary_player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_events",
    )
    secondary_player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secondary_events",
    )
    tertiary_player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tertiary_events",
    )
    goalie = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goalie_events",
    )

    shot_type = models.CharField(max_length=32, null=True, blank=True)
    penalty_type = models.CharField(max_length=64, null=True, blank=True)
    penalty_minutes = models.IntegerField(null=True, blank=True)
    miss_reason = models.CharField(max_length=64, null=True, blank=True)

    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["type_desc", "primary_player"]),
            models.Index(fields=["type_desc", "secondary_player"]),
            models.Index(fields=["type_desc", "goalie"]),
            models.Index(fields=["game", "period", "period_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.type_desc} @ {self.game_id}"
