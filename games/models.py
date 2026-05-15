from django.db import models


class Game(models.Model):
    """One row per NHL game. `id` is the NHL game_id (YYYYTTNNNN encoding)."""

    TYPE_PRESEASON = 1
    TYPE_REGULAR = 2
    TYPE_PLAYOFF = 3
    TYPE_ALLSTAR = 4
    TYPE_CHOICES = [
        (TYPE_PRESEASON, "Preseason"),
        (TYPE_REGULAR, "Regular Season"),
        (TYPE_PLAYOFF, "Playoff"),
        (TYPE_ALLSTAR, "All-Star / Other"),
    ]

    id = models.IntegerField(primary_key=True)
    season = models.IntegerField(db_index=True)  # e.g. 19421943
    game_type = models.SmallIntegerField(choices=TYPE_CHOICES)
    game_date = models.DateField(db_index=True)
    start_time_utc = models.DateTimeField(null=True, blank=True)

    home_team = models.CharField(max_length=3)
    away_team = models.CharField(max_length=3)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)

    venue = models.CharField(max_length=128, null=True, blank=True)
    game_state = models.CharField(max_length=8, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["season", "game_type"]),
            models.Index(fields=["home_team"]),
            models.Index(fields=["away_team"]),
        ]

    def __str__(self) -> str:
        return f"{self.id}: {self.away_team} @ {self.home_team} ({self.game_date})"
