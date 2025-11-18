"""
Database Schemas for OTT Platform

Each Pydantic model represents a collection in MongoDB (collection name is the lowercase of the class name).
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import datetime

class Content(BaseModel):
    """
    Movies/Series content metadata
    Collection: "content"
    """
    title: str = Field(..., description="Title of the content")
    type: Literal["movie", "series"] = Field(..., description="Content type")
    description: Optional[str] = Field(None)
    year: Optional[int] = Field(None)
    genres: List[str] = Field(default_factory=list)
    maturity_rating: Optional[str] = Field(None)
    duration_minutes: Optional[int] = Field(None, description="For movies")
    seasons: Optional[int] = Field(None, description="For series")
    episodes: Optional[List[Dict]] = Field(default=None, description="List of episodes with {season, episode, title, duration}")
    poster_url: Optional[str] = Field(None)
    backdrop_url: Optional[str] = Field(None)
    trailer_url: Optional[str] = Field(None)
    stream_url: Optional[str] = Field(None, description="HLS/DASH URL for adaptive streaming")
    tags: List[str] = Field(default_factory=list)
    popularity: int = Field(0, description="Rolling popularity score")

class Userprofile(BaseModel):
    """
    User profile & settings
    Collection: "userprofile"
    """
    user_id: str = Field(..., description="Firebase auth uid or email")
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    favorites: List[str] = Field(default_factory=list, description="List of content _id strings")
    watch_history: List[Dict] = Field(default_factory=list, description="Recent watches: {content_id, position, completed, last_watched_at}")
    created_at: Optional[datetime] = None

class Watchevent(BaseModel):
    """
    Watch telemetry events
    Collection: "watchevent"
    """
    user_id: str
    content_id: str
    position_seconds: int = 0
    duration_seconds: Optional[int] = None
    completed: bool = False
    device: Optional[str] = None
    network: Optional[str] = None
    created_at: Optional[datetime] = None
