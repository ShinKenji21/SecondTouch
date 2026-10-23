"""Pydantic models for the data that crosses a boundary: viewer settings coming
in over the WebSocket, model output coming back from Azure OpenAI, and the
event itself (validated in the tests, and on every event when VALIDATE_EVENTS=1)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Mode = Literal["ANALYST", "CASUAL", "PLAYER_CAM"]
Lang = Literal["en", "es", "ja"]
EventType = Literal["PASS", "DRIBBLE", "SHOT", "TACKLE", "SUBSTITUTION", "HALF_TIME", "FULL_TIME"]
SetPiece = Literal["FREE_KICK", "CORNER", "THROW_IN", "PENALTY", "GOAL_KICK"]
OUTCOMES = {
    "PASS": {"COMPLETE", "INTERCEPTED", "OUT", "OFFSIDE"}, "DRIBBLE": {"SUCCESS"}, "TACKLE": {"WON", "FOUL"},
    "SHOT": {"GOAL", "SAVED", "MISS", "BLOCKED"},
}


class ClientConfig(BaseModel):
    """Viewer settings. Every field is optional so a client can send only what changed."""
    mode: Optional[Mode] = None
    team: Optional[str] = None
    player: Optional[str] = None
    speed: Optional[int] = None
    lang: Optional[Lang] = None
    interval: Optional[float] = None
    fav_team: Optional[Literal["NONE", "Brackenford", "Kestermouth"]] = None  # favourite club, "NONE" for neutral

    @field_validator("speed")
    @classmethod
    def _speed(cls, v):
        return v if v in (1, 4, 10) else 1

    @field_validator("interval")
    @classmethod
    def _interval(cls, v):
        return None if v is None else min(2.0, max(1.0, float(v)))


class PersonaCommentary(BaseModel):
    """What the model must return for one impact moment."""
    analyst: str = Field(min_length=8, max_length=320)
    casual: str = Field(min_length=4, max_length=240)
    player_cam: str = Field(min_length=8, max_length=320)


class Location(BaseModel):
    start_x: float
    start_y: float
    end_x: float
    end_y: float


class Metrics(BaseModel):
    xg: Optional[float] = None
    pass_difficulty: Optional[int] = None
    pressure: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    pressure_index: Optional[int] = None
    nearest_defender_m: Optional[float] = None
    sprint_speed_kmh: Optional[float] = None
    ball_speed_kmh: Optional[float] = None
    forward_gain_m: Optional[float] = None
    players_bypassed: Optional[int] = None


class Event(BaseModel):
    seq: int
    minute: float
    clock: str
    team: Optional[str]
    player: Optional[str]
    event_type: EventType
    outcome: Optional[str]
    opponent: Optional[str] = None
    receiver: Optional[str] = None
    player_off: Optional[str] = None
    card: Optional[Literal["YELLOW", "RED"]] = None
    set_piece: Optional[SetPiece] = None          # this action restarts play (corner, free kick, ...)
    restart: Optional[SetPiece] = None            # play stopped after this action; this restart follows
    restart_team: Optional[str] = None            # who takes that restart
    body_part: Optional[Literal["FOOT", "HEAD"]] = None  # shots only
    length_m: Optional[float] = None
    location: Location
    metrics: Metrics
    score: dict
    is_impact_moment: bool = False
    impact_reasons: list[str] = []
    possession_change: bool = False
    right_team: str
    generated_at: float

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, v, info):
        allowed = OUTCOMES.get(info.data.get("event_type"))
        if allowed is not None and v not in allowed:
            raise ValueError(f"{v} is not an outcome of {info.data.get('event_type')}")
        return v
