"""Pydantic models for the data that crosses a boundary: viewer settings coming
in over the WebSocket, model output coming back from Azure OpenAI, and the
event itself (validated in the tests, and on every event when VALIDATE_EVENTS=1)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Mode = Literal["ANALYST", "CASUAL", "PLAYER_CAM"]
Lang = Literal["en", "es", "ja"]
EventType = Literal["PASS", "DRIBBLE", "SHOT", "TACKLE", "SUBSTITUTION", "HALF_TIME", "FULL_TIME"]


class ClientConfig(BaseModel):
    """Viewer settings. Every field is optional so a client can send only what changed."""
    mode: Optional[Mode] = None
    team: Optional[str] = None
    player: Optional[str] = None
    speed: Optional[int] = None
    lang: Optional[Lang] = None
    interval: Optional[float] = None

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
    length_m: Optional[float] = None
    location: Location
    metrics: Metrics
    score: dict
    is_impact_moment: bool = False
    impact_reasons: list[str] = []
    generated_at: float
