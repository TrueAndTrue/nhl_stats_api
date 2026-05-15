from django.db import models


class Player(models.Model):
    """One row per NHL player, keyed by the league's own player ID."""

    POS_CENTER = "C"
    POS_LEFT_WING = "L"
    POS_RIGHT_WING = "R"
    POS_DEFENSE = "D"
    POS_GOALIE = "G"
    POSITION_CHOICES = [
        (POS_CENTER, "Center"),
        (POS_LEFT_WING, "Left Wing"),
        (POS_RIGHT_WING, "Right Wing"),
        (POS_DEFENSE, "Defense"),
        (POS_GOALIE, "Goalie"),
    ]

    HAND_LEFT = "L"
    HAND_RIGHT = "R"
    HAND_CHOICES = [(HAND_LEFT, "Left"), (HAND_RIGHT, "Right")]

    nhl_api_id = models.IntegerField(primary_key=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    full_name = models.CharField(max_length=256, db_index=True)
    player_slug = models.CharField(max_length=128, null=True, blank=True)

    is_active = models.BooleanField(default=False)
    sweater_number = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=2, choices=POSITION_CHOICES)
    shoots_catches = models.CharField(
        max_length=1, choices=HAND_CHOICES, null=True, blank=True
    )

    headshot_url = models.URLField(max_length=512, null=True, blank=True)
    hero_image_url = models.URLField(max_length=512, null=True, blank=True)

    birth_date = models.DateField(null=True, blank=True)
    birth_city = models.CharField(max_length=128, null=True, blank=True)
    birth_state_province = models.CharField(max_length=128, null=True, blank=True)
    birth_country = models.CharField(max_length=3, null=True, blank=True)

    height_cm = models.IntegerField(null=True, blank=True)
    weight_kg = models.IntegerField(null=True, blank=True)

    in_hhof = models.BooleanField(default=False)
    in_top_100 = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["player_slug"]),
            models.Index(fields=["position"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"
