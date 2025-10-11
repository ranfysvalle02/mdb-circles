import os
import re
import secrets
import json
import time
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union, Callable, Literal, Dict
from contextlib import asynccontextmanager
from enum import Enum
from urllib.parse import urlparse

import uvicorn
import jwt
import requests
import openai
from bs4 import BeautifulSoup
from jwt.exceptions import PyJWTError
from fastapi import FastAPI, HTTPException, Body, Depends, status, Query, Request, Path
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field, AnyHttpUrl, ConfigDict, ValidationError
from passlib.context import CryptContext
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from bson import ObjectId
from pydantic_core import core_schema
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

import cloudinary
import cloudinary.uploader
import cloudinary.api

from dotenv import load_dotenv
load_dotenv()

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key-that-you-should-change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
INVITE_TOKEN_EXPIRE_HOURS = 24

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
  openai.api_key = OPENAI_API_KEY
  print("OpenAI client configured.")
else:
  print("Warning: OPENAI_API_KEY not found. AI features will be disabled.")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
  cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
  )
  print("Cloudinary configured.")
else:
  print("Warning: Cloudinary credentials not found. Image uploads will be disabled.")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
if all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET]):
  print("Spotify credentials configured.")
else:
  print("Warning: Spotify credentials not found. Spotify features will be disabled.")

client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
db = client.circles_app

users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
invite_tokens_collection = db.get_collection("invite_tokens")
invitations_collection = db.get_collection("invitations")
notifications_collection = db.get_collection("notifications")
comments_collection = db.get_collection("comments")
activity_events_collection = db.get_collection("activity_events")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ==============================================================================
# LIFESPAN & APP SETUP
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
  users_collection.create_index([("username", ASCENDING)], unique=True)
  circles_collection.create_index([("name", ASCENDING)])
  circles_collection.create_index([("members.user_id", ASCENDING)])
  posts_collection.create_index([("circle_id", ASCENDING)])
  posts_collection.create_index([("created_at", DESCENDING)])
  posts_collection.create_index([("content.tags", ASCENDING)])
  posts_collection.create_index([("chat_participants.user_id", ASCENDING)])
  invite_tokens_collection.create_indexes([IndexModel([("expires_at", DESCENDING)], expireAfterSeconds=0)])
  invitations_collection.create_index(
    [("circle_id", ASCENDING), ("invitee_id", ASCENDING)],
    unique=True,
    partialFilterExpression={"status": "pending"}
  )
  invitations_collection.create_index([("invitee_id", ASCENDING), ("status", ASCENDING)])
  notifications_collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
  comments_collection.create_index([("post_id", ASCENDING)])
  comments_collection.create_index([("thread_user_id", ASCENDING)])
  activity_events_collection.create_index([("notified_user_ids", ASCENDING)])
  activity_events_collection.create_index([("timestamp", DESCENDING)])

  print("Database indexes ensured.")
  yield
  client.close()

app = FastAPI(
  title="Circles Social API",
  description="A complete API with user auth, circles, posts, and real-time features.",
  version="8.0.1", # Version bump
  lifespan=lifespan,
)

origins = ["*"]
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

class PermissionsPolicyMiddleware(BaseHTTPMiddleware):
  async def dispatch(self, request: Request, call_next: Callable) -> StarletteResponse:
    response = await call_next(request)
    response.headers['Permissions-Policy'] = 'compute-pressure=(self "https://www.youtube.com")'
    return response

app.add_middleware(PermissionsPolicyMiddleware)


# ==============================================================================
# MODELS
# ==============================================================================
class PyObjectId(ObjectId):
  @classmethod
  def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> core_schema.CoreSchema:
    def validate(v):
      if not ObjectId.is_valid(v):
        raise ValueError('Invalid ObjectId')
      return ObjectId(v)
    return core_schema.json_or_python_schema(
      json_schema=core_schema.str_schema(),
      python_schema=core_schema.union_schema([
        core_schema.is_instance_schema(ObjectId),
        core_schema.no_info_plain_validator_function(validate),
      ]),
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda instance: str(instance)
      ),
    )

class RoleEnum(str, Enum):
  member = "member"
  moderator = "moderator"
  admin = "admin"

class InvitationStatusEnum(str, Enum):
  pending = "pending"
  accepted = "accepted"
  rejected = "rejected"

class NotificationTypeEnum(str, Enum):
  invite_received = "invite_received"
  invite_accepted = "invite_accepted"
  invite_rejected = "invite_rejected"
  new_comment = "new_comment"
  chat_invite = "chat_invite"
  new_chat_message = "new_chat_message"

class ActivityEventTypeEnum(str, Enum):
  new_post = "new_post"
  new_comment = "new_comment"

class SortByEnum(str, Enum):
  newest = "newest"

class PostTypeEnum(str, Enum):
  standard = "standard"
  yt_playlist = "yt-playlist"
  poll = "poll"
  wishlist = "wishlist"
  image = "image"
  spotify_playlist = "spotify_playlist"

class UserRegister(BaseModel):
  username: str = Field(...)
  password: str = Field(...)

class UserAuth(BaseModel):
  username: str
  password: str

class UserInDB(BaseModel):
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
  username: str
  password_hash: str
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class UserOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  username: str
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class UserMeOut(UserOut):
  pass

class TokenResponse(BaseModel):
  access_token: str
  refresh_token: str
  token_type: str = "bearer"

class TokenRefreshRequest(BaseModel):
  refresh_token: str

class CircleMember(BaseModel):
  user_id: PyObjectId
  username: str
  role: RoleEnum = RoleEnum.member
  invited_by: Optional[PyObjectId] = None
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class CircleCreate(BaseModel):
  name: str = Field(..., min_length=3, max_length=100)
  description: Optional[str] = Field(None, max_length=500)
  is_public: bool = False

class CircleUpdate(BaseModel):
  name: str = Field(..., min_length=3, max_length=100)
  description: Optional[str] = Field(None, max_length=500)
  is_public: bool

class CircleOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  name: str
  description: Optional[str]
  owner_id: PyObjectId
  member_count: int
  user_role: Optional[RoleEnum] = None
  is_public: bool = False
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class CircleManagementOut(CircleOut):
  members: List[CircleMember] = []

class MemberRoleUpdate(BaseModel):
  role: RoleEnum

class InviteTokenCreateResponse(BaseModel):
  token: str
  expires_at: datetime

class UserInviteRequest(BaseModel):
  username: str = Field(..., min_length=1)

class InvitationOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  circle_id: PyObjectId
  circle_name: str
  inviter_id: PyObjectId
  inviter_username: str
  created_at: datetime
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class NotificationContent(BaseModel):
  circle_id: Optional[str] = None
  circle_name: Optional[str] = None
  inviter_username: Optional[str] = None
  invitee_username: Optional[str] = None
  model_config = ConfigDict(extra='allow')

class NotificationOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  type: NotificationTypeEnum
  content: NotificationContent
  is_read: bool
  created_at: datetime
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class ActivityEventOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  circle_id: PyObjectId
  post_id: Optional[PyObjectId] = None
  actor_id: PyObjectId
  actor_username: str
  event_type: ActivityEventTypeEnum
  timestamp: datetime
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class JoinByTokenRequest(BaseModel):
  token: str

class JoinByTokenResponse(BaseModel):
  circle_id: str
  circle_name: str

class YouTubeVideo(BaseModel):
  id: str
  title: str
  imageSrc: str

class PlaylistData(BaseModel):
  name: str
  videos: list[YouTubeVideo]

class PollOption(BaseModel):
  text: str = Field(..., min_length=1, max_length=100)

class PollData(BaseModel):
  question: str = Field(..., min_length=1, max_length=280)
  options: list[PollOption] = Field(..., min_items=2, max_items=10)

class ImageData(BaseModel):
  url: AnyHttpUrl
  public_id: str
  height: int
  width: int
  caption: Optional[str] = Field(None, max_length=2200)

class WishlistItem(BaseModel):
  url: AnyHttpUrl
  title: str
  description: Optional[str] = None
  image: Optional[AnyHttpUrl] = None

class SpotifyPlaylistData(BaseModel):
  playlist_name: str
  embed_url: str
  spotify_url: AnyHttpUrl
  playlist_art_url: Optional[AnyHttpUrl] = None


class PostCreate(BaseModel):
    post_type: PostTypeEnum = PostTypeEnum.standard
    text: Optional[str] = Field(None, max_length=10000)
    link: Optional[str] = Field(None)
    tags: list[str] = Field(default_factory=list)
    playlist_data: Optional[PlaylistData] = None
    poll_data: Optional[PollData] = None
    wishlist_data: Optional[List[WishlistItem]] = None
    image_data: Optional[ImageData] = None
    poll_duration_hours: Optional[int] = None
    spotify_playlist_data: Optional[SpotifyPlaylistData] = None
    is_chat_enabled: bool = False
    chat_participant_ids: Optional[List[PyObjectId]] = None

    def validate_post_content(self):
        if self.post_type == PostTypeEnum.standard and not self.text and not self.link:
            raise ValueError('A standard post must contain either text or a link.')
        if self.post_type == PostTypeEnum.yt_playlist:
            if not self.playlist_data or not self.playlist_data.name or not self.playlist_data.videos:
                raise ValueError('A YouTube playlist post must contain a name and at least one video.')
        if self.post_type == PostTypeEnum.poll:
            if not self.poll_data:
                raise ValueError('A poll post must contain poll_data.')
            if self.poll_duration_hours is None or self.poll_duration_hours <= 0:
                raise ValueError('A poll must have a valid duration.')
        if self.post_type == PostTypeEnum.wishlist and (not self.wishlist_data or len(self.wishlist_data) == 0):
            raise ValueError('A wishlist post must contain at least one item.')
        if self.post_type == PostTypeEnum.image and not self.image_data and not self.link:
            raise ValueError('An image post must contain image_data from an upload or a direct link.')
        if self.post_type == PostTypeEnum.spotify_playlist and not self.link and not self.spotify_playlist_data:
            raise ValueError('A Spotify playlist post must contain a link.')

        self.tags = sorted(set(tag.strip().lower() for tag in self.tags if tag.strip()))
        return self

class ChatParticipant(BaseModel):
  user_id: PyObjectId
  username: str

class PostOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  circle_id: PyObjectId
  circle_name: str
  author_id: PyObjectId
  author_username: str
  content: dict[str, Any]
  created_at: datetime
  seen_by_count: int = 0
  is_seen_by_user: bool = False
  poll_results: Optional[dict] = None
  seen_by_user_objects: Optional[List[dict]] = []
  comment_count: int = 0
  is_chat_enabled: bool = False
  chat_participants: Optional[List[ChatParticipant]] = None
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class SeenUser(BaseModel):
  user_id: PyObjectId
  username: str
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class SeenStatusResponse(BaseModel):
  seen: List[SeenUser]
  unseen: List[SeenUser]

class FeedResponse(BaseModel):
  posts: list[PostOut]
  has_more: bool

class PollVoteRequest(BaseModel):
  option_index: int

class MetadataResponse(BaseModel):
  url: str
  title: Optional[str] = None
  description: Optional[str] = None
  image: Optional[str] = None

class PollFromTextRequest(BaseModel):
  text: str

class CommentCreate(BaseModel):
  content: str = Field(..., min_length=1, max_length=5000)
  thread_user_id: Optional[PyObjectId] = None

class CommentOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  post_id: PyObjectId
  commenter_id: PyObjectId
  commenter_username: str
  content: str
  created_at: datetime
  thread_user_id: PyObjectId
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class CommenterInfo(BaseModel):
  user_id: PyObjectId
  username: str
  comment_count: int
  has_unread: bool

class PostActivityInfo(BaseModel):
  post_id: PyObjectId
  new_comment_count: int

class UserActivityStatusResponse(BaseModel):
  new_server_timestamp: datetime
  new_comment_activity: List[PostActivityInfo]
  new_invites_count: int
  new_notifications_count: int

class SpotifyURLRequest(BaseModel):
  url: AnyHttpUrl

class SpotifyTrack(BaseModel):
  track_name: str
  artist_names: List[str]
  album_name: str
  album_art_url: Optional[AnyHttpUrl] = None
  spotify_url: AnyHttpUrl

class SpotifyPlaylist(BaseModel):
  playlist_name: str
  description: Optional[str] = None
  owner_name: str
  playlist_art_url: Optional[AnyHttpUrl] = None
  spotify_url: AnyHttpUrl
  tracks: List[SpotifyTrack]

class SpotifyMetadataResponse(BaseModel):
  type: Literal["track", "playlist"]
  data: Union[SpotifyTrack, SpotifyPlaylist]

class ChatMessageCreate(BaseModel):
  content: str = Field(..., min_length=1, max_length=5000)

class ChatMessageOut(BaseModel):
  id: PyObjectId = Field(alias="_id")
  sender_id: PyObjectId
  sender_username: str
  content: str
  timestamp: datetime
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class ChatParticipantUpdateRequest(BaseModel):
  participant_ids: List[PyObjectId]


# ==============================================================================
# HELPERS & DEPENDENCIES
# ==============================================================================
def sanitize_password(raw_password: str) -> str:
  encoded = raw_password.encode('utf-8')[:72]
  return encoded.decode('utf-8', 'ignore')

def create_jwt_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
  to_encode = data.copy()
  expire = datetime.now(timezone.utc) + expires_delta
  to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "token_type": token_type})
  return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(username: str) -> str:
  return create_jwt_token(
    data={"sub": username},
    expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    token_type="access"
  )

def create_refresh_token(username: str) -> str:
  return create_jwt_token(
    data={"sub": username},
    expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    token_type="refresh"
  )

async def get_current_user_from_token(token: str) -> Optional["UserInDB"]:
  if not token:
    return None
  try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("token_type") != "access":
      return None
    username = payload.get("sub")
    if not username:
      return None
    username = username.lower()
    user_doc = users_collection.find_one({"username": username})
    if not user_doc:
      return None
    return UserInDB(**user_doc)
  except (PyJWTError, ValueError):
    return None

async def get_optional_current_user(request: Request) -> Optional["UserInDB"]:
  auth_header = request.headers.get("Authorization")
  if not auth_header:
    return None
  try:
    scheme, token = auth_header.split()
    if scheme.lower() != "bearer":
      return None
    return await get_current_user_from_token(token)
  except ValueError:
    return None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
  credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
  )
  user = await get_current_user_from_token(token)
  if user is None:
    raise credentials_exception
  return user

async def create_notification(user_id: PyObjectId, notification_type: NotificationTypeEnum, content: dict):
  notification_doc = {
    "user_id": user_id,
    "type": notification_type.value,
    "content": content,
    "is_read": False,
    "created_at": datetime.now(timezone.utc)
  }
  notifications_collection.insert_one(notification_doc)

def fix_circle_doc_if_needed(circle: dict) -> dict:
  updated_fields = {}
  if isinstance(circle.get("owner_id"), str) and ObjectId.is_valid(circle["owner_id"]):
    updated_fields["owner_id"] = ObjectId(circle["owner_id"])
  if "members" in circle and isinstance(circle["members"], list):
    new_members = []
    changed = False
    for m in circle["members"]:
      if isinstance(m.get("user_id"), str) and ObjectId.is_valid(m["user_id"]):
        m["user_id"] = ObjectId(m["user_id"])
        changed = True
      new_members.append(m)
    if changed:
      updated_fields["members"] = new_members
  if updated_fields:
    circles_collection.update_one({"_id": circle["_id"]}, {"$set": updated_fields})
    circle.update(updated_fields)
  return circle

async def get_circle_or_404(circle_id: str) -> dict:
  if not ObjectId.is_valid(circle_id):
    raise HTTPException(status_code=400, detail="Invalid Circle ID")
  circle = circles_collection.find_one({"_id": ObjectId(circle_id)})
  if not circle:
    raise HTTPException(status_code=404, detail="Circle not found")
  return fix_circle_doc_if_needed(circle)

async def get_invitation_or_404(invitation_id: str) -> dict:
  if not ObjectId.is_valid(invitation_id):
    raise HTTPException(status_code=400, detail="Invalid Invitation ID")
  invitation = invitations_collection.find_one({"_id": ObjectId(invitation_id)})
  if not invitation:
    raise HTTPException(status_code=404, detail="Invitation not found")
  return invitation

async def get_post_or_404(post_id: str) -> dict:
  if not ObjectId.is_valid(post_id):
    raise HTTPException(status_code=400, detail="Invalid Post ID")
  post = posts_collection.find_one({"_id": ObjectId(post_id)})
  if not post:
    raise HTTPException(status_code=404, detail="Post not found")
  return post

async def get_comment_or_404(comment_id: str) -> dict:
  if not ObjectId.is_valid(comment_id):
    raise HTTPException(status_code=400, detail="Invalid Comment ID")
  comment = comments_collection.find_one({"_id": ObjectId(comment_id)})
  if not comment:
    raise HTTPException(status_code=404, detail="Comment not found")
  return comment

async def check_circle_membership(current_user: UserInDB, circle: dict) -> dict:
  if circle.get('owner_id') == current_user.id:
    is_in_members = any(m['user_id'] == current_user.id for m in circle.get('members', []))
    if not is_in_members:
      new_member_dict = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": RoleEnum.admin.value
      }
      circles_collection.update_one(
        {"_id": circle["_id"]},
        {"$addToSet": {"members": new_member_dict}}
      )
      if "members" not in circle:
        circle["members"] = []
      circle["members"].append(new_member_dict)
    return circle
  if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
    raise HTTPException(status_code=403, detail="You are not a member of this circle.")
  return circle

async def get_circle_and_user_role(circle_id: str, current_user: UserInDB) -> tuple[dict, RoleEnum]:
  circle = await get_circle_or_404(circle_id)
  member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
  if not member_info:
    raise HTTPException(status_code=403, detail="You are not a member of this circle.")
  return circle, RoleEnum(member_info['role'])

async def get_post_and_check_membership(post_id: str, current_user: UserInDB) -> dict:
  post = await get_post_or_404(post_id)
  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)
  return post

def _get_posts_aggregation_pipeline(
  match_stage: dict, sort_stage: dict, skip: int, limit: int, current_user: Optional["UserInDB"]
) -> list[dict]:
  pipeline = [match_stage]
  add_fields_stage = {
    "$addFields": {
      "seen_by_count": {"$size": {"$ifNull": ["$seen_by_details", []]}},
      "comment_count": {"$ifNull": ["$comment_count", 0]},
      "is_chat_enabled": {"$ifNull": ["$is_chat_enabled", False]},
    }
  }
  pipeline.append(add_fields_stage)
  if current_user:
    pipeline.append({
      "$addFields": {
        "is_seen_by_user": {
          "$gt": [{"$size": {"$filter": {"input": {"$ifNull": ["$seen_by_details", []]}, "as": "seen", "cond": {"$eq": ["$$seen.user_id", current_user.id]}}}}, 0]
        },
        "poll_results": {
          "$cond": {
            "if": {"$eq": ["$content.post_type", "poll"]},
            "then": {
              "total_votes": {"$reduce": {"input": "$content.poll_data.options", "initialValue": 0, "in": {"$add": ["$$value", {"$size": {"$ifNull": ["$$this.votes", []]}}]}}},
              "options": {"$map": {"input": "$content.poll_data.options", "as": "option", "in": {"text": "$$option.text", "votes": {"$size": {"$ifNull": ["$$option.votes", []]}}}}},
              "user_voted_index": {"$indexOfArray": [{"$map": {"input": "$content.poll_data.options", "as": "option", "in": {"$in": [current_user.id, {"$ifNull": ["$$option.votes", []]}]}}}, True]},
              "is_expired": {"$gt": [datetime.now(timezone.utc), "$content.expires_at"]},
              "expires_at": "$content.expires_at"
            },
            "else": "$$REMOVE"
          }
        },
        "chat_participants": {
          "$cond": {
            "if": {
              "$and": [
                {"$eq": ["$is_chat_enabled", True]},
                {"$in": [current_user.id, {"$ifNull": ["$chat_participants.user_id", []]}]}
              ]
            },
            "then": "$chat_participants",
            "else": "$$REMOVE"
          }
        }
      }
    })
  pipeline.extend([
    {"$addFields": {"seen_by_sample_ids": {"$slice": [{"$ifNull": ["$seen_by_details.user_id", []]}, 4]}}},
    {"$lookup": {"from": "users", "localField": "seen_by_sample_ids", "foreignField": "_id", "as": "seen_by_user_objects", "pipeline": [{"$project": {"username": 1, "_id": 0}}]}},
    sort_stage,
    {"$skip": skip},
    {"$limit": limit},
    {"$project": {"seen_by_sample_ids": 0, "content.poll_data.options.votes": 0, "seen_by_details": 0}}
  ])
  return pipeline

SPOTIFY_ACCESS_TOKEN = None
SPOTIFY_TOKEN_EXPIRES_AT = None

async def get_spotify_access_token() -> str:
  """Obtains and caches a Spotify Application Access Token."""
  global SPOTIFY_ACCESS_TOKEN, SPOTIFY_TOKEN_EXPIRES_AT

  now = datetime.now(timezone.utc)
  if SPOTIFY_ACCESS_TOKEN and SPOTIFY_TOKEN_EXPIRES_AT and now < SPOTIFY_TOKEN_EXPIRES_AT - timedelta(seconds=60):
    return SPOTIFY_ACCESS_TOKEN

  if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET]):
    raise HTTPException(status_code=503, detail="Spotify service is not configured on the server.")

  auth_url = 'https://accounts.spotify.com/api/token'
  auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
  auth_header_val = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')

  try:
    response = requests.post(
      auth_url,
      headers={'Authorization': f'Basic {auth_header_val}', 'Content-Type': 'application/x-www-form-urlencoded'},
      data={'grant_type': 'client_credentials'}
    )
    response.raise_for_status()
    token_data = response.json()
    
    access_token = token_data.get('access_token')
    expires_in = token_data.get('expires_in', 3600)
    
    if not access_token:
      raise HTTPException(status_code=502, detail="Failed to retrieve access token from Spotify.")

    SPOTIFY_ACCESS_TOKEN = access_token
    SPOTIFY_TOKEN_EXPIRES_AT = now + timedelta(seconds=expires_in)
    return SPOTIFY_ACCESS_TOKEN

  except requests.RequestException as e:
    raise HTTPException(status_code=502, detail=f"Could not connect to Spotify authentication service: {e}")


# ==============================================================================
# ENDPOINTS
# ==============================================================================
@app.get("/utils/cloudinary-signature", tags=["Utilities"])
async def get_cloudinary_signature(current_user: UserInDB = Depends(get_current_user)):
  if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    raise HTTPException(status_code=503, detail="Cloudinary service is not configured on the server.")
  timestamp = int(time.time())
  params_to_sign = {"timestamp": timestamp}
  signature = cloudinary.utils.api_sign_request(params_to_sign, CLOUDINARY_API_SECRET)
  return {"signature": signature, "timestamp": timestamp, "api_key": CLOUDINARY_API_KEY, "cloud_name": CLOUDINARY_CLOUD_NAME}

@app.get("/utils/extract-metadata", response_model=MetadataResponse, tags=["Utilities"])
async def extract_metadata(url: AnyHttpUrl, current_user: UserInDB = Depends(get_current_user)):
  try:
    headers = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')}
    resp = requests.get(str(url), headers=headers, timeout=5, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")
    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    description_tag = (soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"}))
    image_tag = soup.find("meta", property="og:image")
    image_url = image_tag.get("content") if image_tag else None
    if image_url and ('1x1' in image_url or 'trans.gif' in image_url): image_url = None
    return MetadataResponse(
      url=str(url),
      title=(title_tag.get("content", title_tag.text).strip() if title_tag else "No title found"),
      description=(description_tag.get("content").strip() if description_tag else "No description available."),
      image=image_url
    )
  except requests.RequestException as e:
    raise HTTPException(status_code=400, detail=f"Could not fetch URL metadata: {e}")

@app.post("/utils/generate-poll-from-text", tags=["Utilities"])
async def generate_poll_from_text(request: PollFromTextRequest, current_user: UserInDB = Depends(get_current_user)):
  if not OPENAI_API_KEY:
    raise HTTPException(status_code=503, detail="AI service is not configured on the server.")
  system_prompt = """
  You are an intelligent assistant that converts natural language text into a structured poll.
  Analyze the user's text to identify a clear question and a list of distinct options.
  You must respond ONLY with a JSON object in the following format:
  {"question": "The extracted poll question", "options": [{"text": "Option 1"}, {"text": "Option 2"}, ...]}
  """
  try:
    response = openai.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": request.text}], response_format={"type": "json_object"})
    poll_json = json.loads(response.choices[0].message.content)
    if "question" not in poll_json or "options" not in poll_json or not isinstance(poll_json["options"], list):
      raise ValueError("Invalid JSON structure from AI.")
    formatted_options = [{"text": opt["text"]} if isinstance(opt, dict) else {"text": str(opt)} for opt in poll_json["options"]]
    if len(formatted_options) < 2:
      raise ValueError("AI could not identify at least two poll options.")
    return {"question": poll_json["question"], "options": formatted_options}
  except (openai.APIError, json.JSONDecodeError, ValueError) as e:
    raise HTTPException(status_code=500, detail=f"Failed to generate poll from text: {e}")

@app.post("/utils/spotify-metadata", response_model=SpotifyMetadataResponse, tags=["Utilities"])
async def get_spotify_metadata(body: SpotifyURLRequest, current_user: UserInDB = Depends(get_current_user)):
  url_str = str(body.url)
  match = re.search(r'(?:https?:\/\/open\.spotify\.com\/(?:user\/[^\/]+\/)?|spotify:)(playlist|track)[\/:]([a-zA-Z0-9]+)', url_str)
  if not match:
    raise HTTPException(status_code=400, detail="Invalid Spotify track or playlist URL format.")
  
  item_type, item_id = match.groups()
  access_token = await get_spotify_access_token()
  headers = {'Authorization': f'Bearer {access_token}'}
  
  try:
    if item_type == "track":
      api_url = f'https://api.spotify.com/v1/tracks/{item_id}'
      response = requests.get(api_url, headers=headers)
      response.raise_for_status()
      track_data = response.json()

      track_info = SpotifyTrack(
        track_name=track_data.get('name', 'N/A'),
        artist_names=[artist['name'] for artist in track_data.get('artists', [])],
        album_name=track_data.get('album', {}).get('name', 'N/A'),
        album_art_url=(track_data['album']['images'][0]['url'] if track_data.get('album', {}).get('images') else None),
        spotify_url=track_data.get('external_urls', {}).get('spotify')
      )
      return SpotifyMetadataResponse(type="track", data=track_info)

    elif item_type == "playlist":
      api_url = f'https://api.spotify.com/v1/playlists/{item_id}'
      response = requests.get(api_url, headers=headers)
      response.raise_for_status()
      playlist_data = response.json()
      
      tracks = []
      for item in playlist_data.get('tracks', {}).get('items', []):
        track = item.get('track')
        if track:
          track_info = SpotifyTrack(
            track_name=track.get('name', 'N/A'),
            artist_names=[artist['name'] for artist in track.get('artists', [])],
            album_name=track.get('album', {}).get('name', 'N/A'),
            album_art_url=(track['album']['images'][0]['url'] if track.get('album', {}).get('images') else None),
            spotify_url=track.get('external_urls', {}).get('spotify')
          )
          tracks.append(track_info)
      
      playlist_info = SpotifyPlaylist(
        playlist_name=playlist_data.get('name', 'N/A'),
        description=playlist_data.get('description'),
        owner_name=playlist_data.get('owner', {}).get('display_name', 'N/A'),
        playlist_art_url=(playlist_data['images'][0]['url'] if playlist_data.get('images') else None),
        spotify_url=playlist_data.get('external_urls', {}).get('spotify'),
        tracks=tracks
      )
      return SpotifyMetadataResponse(type="playlist", data=playlist_info)

  except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
      raise HTTPException(status_code=404, detail=f"Spotify {item_type} with ID '{item_id}' not found.")
    raise HTTPException(status_code=502, detail=f"Error communicating with Spotify API: {e.response.text}")
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# ----------------------------------
# Authentication
# ----------------------------------
@app.post("/auth/register", response_model=UserOut, status_code=201, tags=["Authentication"])
async def register_user(user_data: UserRegister):
  if users_collection.find_one({"username": user_data.username.lower()}):
    raise HTTPException(status_code=400, detail="Username already registered")
  safe_password = sanitize_password(user_data.password)
  new_user_doc = {"username": user_data.username.lower(), "password_hash": pwd_context.hash(safe_password)}
  result = users_collection.insert_one(new_user_doc)
  created_user = users_collection.find_one({"_id": result.inserted_id})
  return UserOut(**created_user)

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login_for_access_token(form_data: UserAuth, current_user: Optional[UserInDB] = Depends(get_optional_current_user)):
  if current_user is not None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Already authenticated. Logout before attempting to log in again.")
  user = users_collection.find_one({"username": form_data.username.lower()})
  if not user:
    raise HTTPException(status_code=401, detail="Incorrect username or password")
  safe_password = sanitize_password(form_data.password)
  if not pwd_context.verify(safe_password, user["password_hash"]):
    raise HTTPException(status_code=401, detail="Incorrect username or password")
  access_token = create_access_token(user["username"])
  refresh_token = create_refresh_token(user["username"])
  return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@app.post("/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
async def refresh_access_token(body: TokenRefreshRequest):
  credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"})
  try:
    payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("token_type") != "refresh":
      raise credentials_exception
    username = payload.get("sub")
    if not username:
      raise credentials_exception
  except PyJWTError:
    raise credentials_exception
  user_doc = users_collection.find_one({"username": username})
  if not user_doc:
    raise credentials_exception
  new_access_token = create_access_token(username)
  new_refresh_token = create_refresh_token(username)
  return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)

# ----------------------------------
# Users
# ----------------------------------
@app.get("/users/me", response_model=UserMeOut, tags=["Users"])
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
  return UserMeOut(**current_user.model_dump(by_alias=True))

@app.get("/users/me/invitations", response_model=List[InvitationOut], tags=["Users"])
async def get_my_invitations(current_user: UserInDB = Depends(get_current_user)):
  pipeline = [
    {"$match": {"invitee_id": current_user.id, "status": InvitationStatusEnum.pending.value}},
    {"$lookup": {"from": "circles", "localField": "circle_id", "foreignField": "_id", "as": "circle_info"}},
    {"$unwind": "$circle_info"},
    {"$lookup": {"from": "users", "localField": "inviter_id", "foreignField": "_id", "as": "inviter_info"}},
    {"$unwind": "$inviter_info"},
    {"$project": {
      "_id": 1,
      "circle_id": 1,
      "inviter_id": 1,
      "created_at": 1,
      "circle_name": "$circle_info.name",
      "inviter_username": "$inviter_info.username"
    }}
  ]
  invitations_cursor = invitations_collection.aggregate(pipeline)
  return [InvitationOut(**inv) for inv in invitations_cursor]

@app.get("/users/me/notifications", response_model=List[NotificationOut], tags=["Users"])
async def get_my_notifications(
  current_user: UserInDB = Depends(get_current_user),
  skip: int = Query(0, ge=0),
  limit: int = Query(20, ge=1, le=100),
  unread_only: bool = Query(False)
):
  query = {"user_id": current_user.id}
  if unread_only:
    query["is_read"] = False
  notifications_cursor = notifications_collection.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
  return [NotificationOut(**n) for n in notifications_cursor]

@app.post("/users/me/notifications/read-all", status_code=204, tags=["Users"])
async def mark_all_notifications_as_read(current_user: UserInDB = Depends(get_current_user)):
  notifications_collection.update_many({"user_id": current_user.id, "is_read": False}, {"$set": {"is_read": True}})
  return Response(status_code=204)

@app.get("/users/me/activity-feed", response_model=List[ActivityEventOut], tags=["Users"])
async def get_user_activity_feed(current_user: UserInDB = Depends(get_current_user)):
  events_cursor = activity_events_collection.find(
    {"notified_user_ids": current_user.id}
  ).sort("timestamp", DESCENDING)

  valid_events = []
  processed_event_ids = []

  for event in events_cursor:
    try:
      valid_event_model = ActivityEventOut(**event)
      valid_events.append(valid_event_model.model_dump(by_alias=True))
      processed_event_ids.append(event["_id"])
    except ValidationError as e:
      print(f"Skipping malformed activity event with ID {event.get('_id', 'N/A')}: {e}")
      continue

  if processed_event_ids:
    activity_events_collection.update_many(
      {"_id": {"$in": processed_event_ids}},
      {"$pull": {"notified_user_ids": current_user.id}}
    )
  
  return valid_events
  
# ----------------------------------
# Circles
# ----------------------------------
@app.get("/circles/mine", response_model=List[CircleOut], tags=["Circles"])
async def list_my_circles(current_user: UserInDB = Depends(get_current_user)):
  circles_cursor = circles_collection.find({"members.user_id": current_user.id}).sort("name", ASCENDING)
  result = []
  for c in circles_cursor:
    member_info = next((m for m in c.get('members', []) if m['user_id'] == current_user.id), None)
    user_role = RoleEnum(member_info['role']) if member_info else None
    item = CircleOut(**c, member_count=len(c.get("members", [])), user_role=user_role)
    result.append(item)
  return result

@app.post("/circles", response_model=CircleOut, status_code=201, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
  existing_circle = circles_collection.find_one({
    "members.user_id": current_user.id,
    "name": {"$regex": f"^{re.escape(circle_data.name)}$", "$options": "i"}
  })
  if existing_circle:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"You are already in a circle named '{existing_circle['name']}'. Please choose a different name."
    )

  first_member_doc = {
    "user_id": current_user.id,
    "username": current_user.username,
    "role": RoleEnum.admin.value
  }
  now = datetime.now(timezone.utc)
  new_circle_doc = {
    "name": circle_data.name, "description": circle_data.description, "owner_id": current_user.id,
    "members": [first_member_doc], "created_at": now, "is_public": circle_data.is_public
  }
  result = circles_collection.insert_one(new_circle_doc)
  created_circle = circles_collection.find_one({"_id": result.inserted_id})
  return CircleOut(**created_circle, member_count=1, user_role=RoleEnum.admin)

@app.post("/circles/{circle_id}/invite-token", response_model=InviteTokenCreateResponse, tags=["Circles"])
async def create_invite_token(circle_id: str, current_user: UserInDB = Depends(get_current_user)):
  circle = await get_circle_or_404(circle_id)
  await check_circle_membership(current_user, circle)
  while True:
    token = secrets.token_urlsafe(24)
    if not invite_tokens_collection.find_one({"token": token}):
      break
  expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_TOKEN_EXPIRE_HOURS)
  invite_tokens_collection.insert_one({"token": token, "circle_id": circle["_id"], "expires_at": expires_at, "inviter_id": current_user.id})
  return InviteTokenCreateResponse(token=token, expires_at=expires_at)

@app.post("/circles/{circle_id}/invite-user", status_code=201, tags=["Circles"])
async def invite_user_to_circle(
  circle_id: str,
  invite_data: UserInviteRequest,
  current_user: UserInDB = Depends(get_current_user)
):
  circle = await get_circle_or_404(circle_id)
  await check_circle_membership(current_user, circle)

  invitee = users_collection.find_one({"username": invite_data.username.lower()})
  if not invitee:
    raise HTTPException(status_code=404, detail="User to invite not found.")

  if invitee["_id"] == current_user.id:
    raise HTTPException(status_code=400, detail="You cannot invite yourself.")

  if any(m['user_id'] == invitee["_id"] for m in circle.get("members", [])):
    raise HTTPException(status_code=400, detail="User is already a member of this circle.")

  existing_invite = invitations_collection.find_one({
    "circle_id": circle["_id"],
    "invitee_id": invitee["_id"],
    "status": InvitationStatusEnum.pending.value
  })
  if existing_invite:
    raise HTTPException(status_code=400, detail="This user already has a pending invitation to this circle.")

  invitation_doc = {
    "circle_id": circle["_id"],
    "inviter_id": current_user.id,
    "invitee_id": invitee["_id"],
    "status": InvitationStatusEnum.pending.value,
    "created_at": datetime.now(timezone.utc)
  }
  invitations_collection.insert_one(invitation_doc)

  await create_notification(
    user_id=invitee["_id"],
    notification_type=NotificationTypeEnum.invite_received,
    content={
      "circle_id": str(circle["_id"]),
      "circle_name": circle["name"],
      "inviter_username": current_user.username
    }
  )
  return {"message": f"Invitation sent to {invitee['username']}."}

@app.post("/circles/join-by-token", response_model=JoinByTokenResponse, tags=["Circles"])
async def join_circle_by_token(body: JoinByTokenRequest, current_user: UserInDB = Depends(get_current_user)):
  token_doc = invite_tokens_collection.find_one({"token": body.token, "expires_at": {"$gt": datetime.now(timezone.utc)}})
  if not token_doc:
    raise HTTPException(status_code=400, detail="Invite link is invalid or has expired.")
  circle = circles_collection.find_one({"_id": token_doc["circle_id"]})
  if not circle:
    raise HTTPException(status_code=404, detail="The circle associated with this invite no longer exists.")
  if any(m['user_id'] == current_user.id for m in circle.get("members", [])):
    return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])
  
  inviter_id = token_doc.get("inviter_id")
  new_member_doc = {
    "user_id": current_user.id,
    "username": current_user.username,
    "role": RoleEnum.member.value,
    "invited_by": inviter_id
  }
  new_member_doc = {k: v for k, v in new_member_doc.items() if v is not None}
  
  circles_collection.update_one(
    {"_id": circle["_id"]},
    {"$addToSet": {"members": new_member_doc}}
  )
  return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])

@app.get("/circles/{circle_id}", response_model=Union[CircleManagementOut, CircleOut], tags=["Circles"])
async def get_circle_details(
  circle_id: str,
  current_user: Optional[UserInDB] = Depends(get_optional_current_user)
):
  circle = await get_circle_or_404(circle_id)
  is_public = circle.get("is_public", False)
  
  user_role: Optional[RoleEnum] = None
  member_info: Optional[Dict] = None

  if current_user:
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    if member_info:
      user_role = RoleEnum(member_info['role'])

  if not is_public:
    if not current_user:
      raise HTTPException(status_code=401, detail="You must be logged in to view this private circle.")
    if not user_role:
      raise HTTPException(status_code=403, detail="You are not a member of this circle.")

  member_count = len(circle.get("members", []))
  
  if user_role in [RoleEnum.admin, RoleEnum.moderator]:
    circle_data = circle.copy()
    raw_members = circle_data.pop("members", [])
    return CircleManagementOut(
      **circle_data,
      member_count=member_count,
      user_role=user_role,
      members=[CircleMember(**m) for m in raw_members]
    )
  else:
    return CircleOut(
      **circle,
      member_count=member_count,
      user_role=user_role
    )

@app.patch("/circles/{circle_id}", response_model=CircleManagementOut, tags=["Circles"])
async def update_circle_settings(circle_id: str, circle_data: CircleUpdate, current_user: UserInDB = Depends(get_current_user)):
  circle, user_role = await get_circle_and_user_role(circle_id, current_user)
  if user_role != RoleEnum.admin:
    raise HTTPException(status_code=403, detail="Only circle admins can change settings.")
  update_doc = {
    "name": circle_data.name,
    "description": circle_data.description,
    "is_public": circle_data.is_public
  }
  circles_collection.update_one({"_id": circle["_id"]}, {"$set": update_doc})
  updated_circle_doc = circles_collection.find_one({"_id": circle["_id"]})
  return await get_circle_details(circle_id, current_user)


@app.delete("/circles/{circle_id}", status_code=204, tags=["Circles"])
async def delete_circle(circle_id: str, current_user: UserInDB = Depends(get_current_user)):
  circle, user_role = await get_circle_and_user_role(circle_id, current_user)
  if user_role != RoleEnum.admin:
    raise HTTPException(status_code=403, detail="Only circle admins can delete the circle.")
  
  posts_in_circle = posts_collection.find({"circle_id": circle["_id"]}, {"_id": 1})
  post_ids_to_delete = [post["_id"] for post in posts_in_circle]

  if post_ids_to_delete:
    comments_collection.delete_many({"post_id": {"$in": post_ids_to_delete}})
  
  posts_collection.delete_many({"circle_id": circle["_id"]})
  circles_collection.delete_one({"_id": circle["_id"]})
  invitations_collection.delete_many({"circle_id": circle["_id"]})
  
  return Response(status_code=204)

@app.patch("/circles/{circle_id}/members/{user_id}", response_model=CircleManagementOut, tags=["Circles"])
async def update_circle_member_role(circle_id: str, user_id: str, role_data: MemberRoleUpdate, current_user: UserInDB = Depends(get_current_user)):
  if not ObjectId.is_valid(user_id):
    raise HTTPException(status_code=400, detail="Invalid User ID")
  target_user_id = ObjectId(user_id)
  circle, user_role = await get_circle_and_user_role(circle_id, current_user)
  target_member = next((m for m in circle.get("members", []) if m['user_id'] == target_user_id), None)
  if not target_member:
    raise HTTPException(status_code=404, detail="Member not found in this circle.")
  if user_role == RoleEnum.admin:
    if target_user_id == circle["owner_id"] and role_data.role != RoleEnum.admin:
      raise HTTPException(status_code=403, detail="The circle owner's role cannot be changed.")
  elif user_role == RoleEnum.moderator:
    if target_member["role"] in [RoleEnum.admin.value, RoleEnum.moderator.value] or role_data.role in [RoleEnum.admin, RoleEnum.moderator]:
      raise HTTPException(status_code=403, detail="Moderators can only manage members.")
  else:
    raise HTTPException(status_code=403, detail="You do not have permission to manage roles.")
  circles_collection.update_one({"_id": circle["_id"], "members.user_id": target_user_id}, {"$set": {"members.$.role": role_data.role.value}})
  return await get_circle_details(circle_id, current_user)

@app.delete("/circles/{circle_id}/members/{user_id}", response_model=CircleManagementOut, tags=["Circles"])
async def kick_circle_member(circle_id: str, user_id: str, current_user: UserInDB = Depends(get_current_user)):
  if not ObjectId.is_valid(user_id):
    raise HTTPException(status_code=400, detail="Invalid User ID")
  target_user_id = ObjectId(user_id)
  if target_user_id == current_user.id:
    raise HTTPException(status_code=400, detail="You cannot kick yourself.")
  circle, user_role = await get_circle_and_user_role(circle_id, current_user)
  target_member = next((m for m in circle.get("members", []) if m['user_id'] == target_user_id), None)
  if not target_member:
      raise HTTPException(status_code=404, detail="Member not found in this circle.")
  if target_user_id == circle["owner_id"]:
    raise HTTPException(status_code=403, detail="The circle owner cannot be kicked.")
  # Allow admins to kick anyone but the owner. Moderators can kick members.
  is_admin = user_role == RoleEnum.admin
  is_moderator = user_role == RoleEnum.moderator
  target_is_member = target_member['role'] == RoleEnum.member.value
  if not (is_admin or (is_moderator and target_is_member)):
      raise HTTPException(status_code=403, detail="You do not have permission to kick this member.")

  circles_collection.update_one({"_id": circle["_id"]}, {"$pull": {"members": {"user_id": target_user_id}}})
  return await get_circle_details(circle_id, current_user)

# ----------------------------------
# Invitations
# ----------------------------------
@app.post("/invitations/{invitation_id}/accept", status_code=200, tags=["Invitations"])
async def accept_invitation(invitation_id: str, current_user: UserInDB = Depends(get_current_user)):
  invitation = await get_invitation_or_404(invitation_id)
  if invitation["invitee_id"] != current_user.id:
    raise HTTPException(status_code=403, detail="This invitation is not for you.")
  if invitation["status"] != InvitationStatusEnum.pending.value:
    raise HTTPException(status_code=400, detail="This invitation is no longer pending.")

  circle = await get_circle_or_404(str(invitation["circle_id"]))

  existing_circle_with_same_name = circles_collection.find_one({
    "_id": {"$ne": circle["_id"]},
    "members.user_id": current_user.id,
    "name": {"$regex": f"^{re.escape(circle['name'])}$", "$options": "i"}
  })
  if existing_circle_with_same_name:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"You are already a member of a different circle named '{circle['name']}'. Cannot join another with the same name."
    )

  if any(m['user_id'] == current_user.id for m in circle.get("members", [])):
    invitations_collection.update_one({"_id": invitation["_id"]}, {"$set": {"status": InvitationStatusEnum.accepted.value}})
    raise HTTPException(status_code=400, detail="You are already a member of this circle.")

  new_member_doc = {
    "user_id": current_user.id,
    "username": current_user.username,
    "role": RoleEnum.member.value,
    "invited_by": invitation.get("inviter_id")
  }
  new_member_doc = {k: v for k, v in new_member_doc.items() if v is not None}
  
  circles_collection.update_one(
    {"_id": circle["_id"]},
    {"$addToSet": {"members": new_member_doc}}
  )
  invitations_collection.update_one({"_id": invitation["_id"]}, {"$set": {"status": InvitationStatusEnum.accepted.value}})

  await create_notification(
    user_id=invitation["inviter_id"],
    notification_type=NotificationTypeEnum.invite_accepted,
    content={
      "circle_id": str(circle["_id"]),
      "circle_name": circle["name"],
      "invitee_username": current_user.username
    }
  )
  return {"message": f"Successfully joined the circle '{circle['name']}'."}

@app.post("/invitations/{invitation_id}/reject", status_code=200, tags=["Invitations"])
async def reject_invitation(invitation_id: str, current_user: UserInDB = Depends(get_current_user)):
  invitation = await get_invitation_or_404(invitation_id)
  if invitation["invitee_id"] != current_user.id:
    raise HTTPException(status_code=403, detail="This invitation is not for you.")
  if invitation["status"] != InvitationStatusEnum.pending.value:
    raise HTTPException(status_code=400, detail="This invitation is no longer pending.")
  
  circle = await get_circle_or_404(str(invitation["circle_id"]))
  invitations_collection.update_one({"_id": invitation["_id"]}, {"$set": {"status": InvitationStatusEnum.rejected.value}})

  await create_notification(
    user_id=invitation["inviter_id"],
    notification_type=NotificationTypeEnum.invite_rejected,
    content={
      "circle_id": str(circle["_id"]),
      "circle_name": circle["name"],
      "invitee_username": current_user.username
    }
  )
  return {"message": "Invitation rejected."}

# ----------------------------------
# Notifications
# ----------------------------------
@app.post("/notifications/{notification_id}/read", status_code=204, tags=["Notifications"])
async def mark_notification_as_read(notification_id: str, current_user: UserInDB = Depends(get_current_user)):
  if not ObjectId.is_valid(notification_id):
    raise HTTPException(status_code=400, detail="Invalid Notification ID")
  
  result = notifications_collection.update_one(
    {"_id": ObjectId(notification_id), "user_id": current_user.id},
    {"$set": {"is_read": True}}
  )
  if result.matched_count == 0:
    raise HTTPException(status_code=404, detail="Notification not found or you don't have permission to read it.")
  return Response(status_code=204)

# ----------------------------------
# Feeds & Posts
# ----------------------------------
@app.get("/circles/{circle_id}/feed", response_model=FeedResponse, tags=["Feeds"])
async def get_circle_feed(
  circle_id: str,
  skip: int = Query(0, ge=0),
  limit: int = Query(10, ge=1, le=50),
  sort_by: SortByEnum = Query(SortByEnum.newest),
  tags: Optional[str] = None,
  current_user: Optional[UserInDB] = Depends(get_optional_current_user)
):
  circle = await get_circle_or_404(circle_id)
  is_public = circle.get("is_public", False)

  if not is_public:
    if not current_user:
      raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="You must be logged in to view this private circle."
      )
    await check_circle_membership(current_user, circle)

  match_query = {"circle_id": ObjectId(circle_id)}
  if tags:
    tag_list = [t.strip().lower() for t in tags.split(',') if t.strip()]
    if tag_list:
      match_query["content.tags"] = {"$all": tag_list}
  
  match_stage = {"$match": match_query}
  total_posts = posts_collection.count_documents(match_query)
  sort_stage = {"$sort": {"created_at": DESCENDING}}
  
  pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
  cursor = posts_collection.aggregate(pipeline)
  
  posts_list = [PostOut(**p, circle_name=circle["name"]) for p in cursor]
  
  return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)



@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=201, tags=["Posts"])
async def create_post_in_circle(circle_id: str, post_data: PostCreate, current_user: UserInDB = Depends(get_current_user)):
    """
    Creates a new post in a specified circle, correctly handling all post types and features like chat.
    """
    circle = await get_circle_or_404(circle_id)
    await check_circle_membership(current_user, circle)

    # --- (Spotify and Cloudinary logic) ---
    if post_data.post_type == PostTypeEnum.spotify_playlist and post_data.link:
        if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET]):
            raise HTTPException(status_code=503, detail="Spotify service is not configured on the server.")
        match = re.search(r'(?:https?:\/\/open\.spotify\.com\/|spotify:)playlist[\/:]([a-zA-Z0-9]+)', post_data.link)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid Spotify playlist URL format.")
        playlist_id = match.groups()[0]
        access_token = await get_spotify_access_token()
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            api_url = f'https://api.spotify.com/v1/playlists/{playlist_id}'
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            playlist_api_data = response.json()
            post_data.spotify_playlist_data = SpotifyPlaylistData(
                playlist_name=playlist_api_data.get('name', 'Spotify Playlist'),
                embed_url=f"https://open.spotify.com/embed/playlist/{playlist_id}?utm_source=generator",
                spotify_url=playlist_api_data.get('external_urls', {}).get('spotify'),
                playlist_art_url=(playlist_api_data['images'][0]['url'] if playlist_api_data.get('images') else None)
            )
            post_data.link = None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Spotify playlist not found.")
            raise HTTPException(status_code=502, detail="Error communicating with Spotify API.")

    is_standard_post_with_image_link = (post_data.post_type == PostTypeEnum.standard and post_data.link and re.search(r'\.(jpg|jpeg|png|gif|webp)$', post_data.link.lower()))
    is_image_post_with_link = (post_data.post_type == PostTypeEnum.image and post_data.link and not post_data.image_data)
    if is_standard_post_with_image_link or is_image_post_with_link:
        if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
            try:
                upload_result = cloudinary.uploader.upload(post_data.link)
                post_data.post_type = PostTypeEnum.image
                post_data.image_data = ImageData(
                    url=upload_result.get("secure_url"),
                    public_id=upload_result.get("public_id"),
                    height=upload_result.get("height"),
                    width=upload_result.get("width"),
                    caption=post_data.text
                )
                post_data.link = None
                post_data.text = None
            except Exception as e:
                print(f"Cloudinary auto-upload failed: {e}")
                post_data.post_type = PostTypeEnum.standard

    try:
        post_data.validate_post_content()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Convert the Pydantic model to a JSON-serializable (and BSON-safe) dictionary
    content_payload = jsonable_encoder(post_data, exclude={
        "is_chat_enabled", "chat_participant_ids", "poll_duration_hours"
    }, exclude_unset=True)

    # Build the final document for MongoDB
    now = datetime.now(timezone.utc)
    new_post_doc = {
        "circle_id": ObjectId(circle_id),
        "author_id": current_user.id,
        "author_username": current_user.username,
        "content": content_payload,
        "created_at": now,
        "seen_by_details": [],
        "comment_count": 0,
        "is_chat_enabled": post_data.is_chat_enabled
    }
    
    # Handle poll-specific fields
    if post_data.post_type == PostTypeEnum.poll and post_data.poll_data:
        if 'options' in new_post_doc["content"]["poll_data"]:
            for option in new_post_doc["content"]["poll_data"]["options"]:
                option["votes"] = []
        if post_data.poll_duration_hours:
            expires_at = now + timedelta(hours=post_data.poll_duration_hours)
            new_post_doc["content"]["expires_at"] = expires_at

    # Handle chat-specific fields if enabled
    if post_data.is_chat_enabled:
        participant_ids = {current_user.id}.union(set(post_data.chat_participant_ids or []))
        
        circle_member_ids = {m['user_id'] for m in circle.get('members', [])}
        if not participant_ids.issubset(circle_member_ids):
            raise HTTPException(status_code=400, detail="All chat participants must be members of the circle.")
        
        participants_cursor = users_collection.find(
            {"_id": {"$in": list(participant_ids)}}, 
            {"_id": 1, "username": 1}
        )
        participant_list = list(participants_cursor)
        participant_docs = [{"user_id": p["_id"], "username": p["username"]} for p in participant_list]

        new_post_doc["chat_participants"] = participant_docs
        new_post_doc["chat_messages"] = []
    
    result = posts_collection.insert_one(new_post_doc)
    
    # Create an activity event for other circle members
    other_member_ids = [
        member['user_id'] for member in circle.get('members', [])
        if member['user_id'] != current_user.id
    ]
    if other_member_ids:
        activity_event = {
            "circle_id": circle["_id"], "post_id": result.inserted_id,
            "actor_id": current_user.id, "actor_username": current_user.username,
            "event_type": ActivityEventTypeEnum.new_post, "timestamp": now,
            "notified_user_ids": other_member_ids
        }
        activity_events_collection.insert_one(activity_event)
    
    # Fetch and return the newly created post
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    if not created_post:
        raise HTTPException(status_code=500, detail="Failed to create and retrieve post.")
    
    return PostOut(**created_post, circle_name=circle["name"], is_seen_by_user=False)



@app.post("/posts/{post_id}/seen", status_code=204, tags=["Posts"])
async def mark_post_as_seen(post_id: str, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)
  posts_collection.update_one({"_id": post["_id"]}, {"$pull": {"seen_by_details": {"user_id": current_user.id}}})
  seen_record = {"user_id": current_user.id, "seen_at": datetime.now(timezone.utc)}
  posts_collection.update_one({"_id": post["_id"]}, {"$addToSet": {"seen_by_details": seen_record}})
  return Response(status_code=204)

@app.get("/posts/{post_id}/seen-status", response_model=SeenStatusResponse, tags=["Posts"])
async def get_post_seen_status(post_id: str, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)
  seen_user_ids = {seen['user_id'] for seen in post.get("seen_by_details", [])}
  seen_users: List[SeenUser] = []
  unseen_users: List[SeenUser] = []
  for member in circle.get("members", []):
    member_info = SeenUser(user_id=member["user_id"], username=member["username"])
    if member["user_id"] in seen_user_ids: seen_users.append(member_info)
    else: unseen_users.append(member_info)
  return SeenStatusResponse(seen=seen_users, unseen=unseen_users)

@app.post("/posts/{post_id}/poll-vote", tags=["Posts"])
async def vote_on_poll(post_id: str, vote_data: PollVoteRequest, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if post.get("content", {}).get("post_type") != "poll":
    raise HTTPException(status_code=400, detail="This post is not a poll.")

  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)

  expires_at = post.get("content", {}).get("expires_at")

  if expires_at and isinstance(expires_at, datetime) and expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)

  if expires_at and datetime.now(timezone.utc) > expires_at:
    raise HTTPException(status_code=403, detail="This poll has closed and is no longer accepting votes.")

  options = post["content"]["poll_data"]["options"]
  if not (0 <= vote_data.option_index < len(options)):
    raise HTTPException(status_code=400, detail="Invalid poll option index.")

  for i in range(len(options)):
    posts_collection.update_one(
      {"_id": post["_id"]},
      {"$pull": {f"content.poll_data.options.{i}.votes": current_user.id}}
    )

  posts_collection.update_one(
    {"_id": post["_id"]},
    {"$addToSet": {f"content.poll_data.options.{vote_data.option_index}.votes": current_user.id}}
  )
  
  pipeline = _get_posts_aggregation_pipeline(
    {"$match": {"_id": post["_id"]}},
    {"$sort": {"_id": 1}},
    0,
    1,
    current_user
  )
  updated_post_cursor = posts_collection.aggregate(pipeline)
  updated_post = list(updated_post_cursor)
  
  if not updated_post:
    raise HTTPException(status_code=404, detail="Post not found after poll vote.")
    
  return {"status": "success", "poll_results": updated_post[0]["poll_results"]}

@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=204, tags=["Posts"])
async def delete_post(circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user)):
  circle = await get_circle_or_404(circle_id)
  if not ObjectId.is_valid(post_id):
    raise HTTPException(status_code=400, detail="Invalid Post ID")
  post = posts_collection.find_one({"_id": ObjectId(post_id), "circle_id": ObjectId(circle_id)})
  if not post:
    raise HTTPException(status_code=404, detail="Post not found in this circle")
  member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
  user_is_mod_or_admin = member_info and RoleEnum(member_info['role']) in [RoleEnum.moderator, RoleEnum.admin]
  if not (post['author_id'] == current_user.id or user_is_mod_or_admin):
    raise HTTPException(status_code=403, detail="You don't have permission to delete this post")
  posts_collection.delete_one({"_id": ObjectId(post_id)})
  comments_collection.delete_many({"post_id": ObjectId(post_id)})
  return Response(status_code=204)

# ----------------------------------
# Comments
# ----------------------------------
@app.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201, tags=["Comments"])
async def create_comment_on_post(post_id: str, comment_data: CommentCreate, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)
  is_author = (current_user.id == post["author_id"])
  if is_author:
    if not comment_data.thread_user_id:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Post authors can only comment by replying to another user's thread.")
    if comment_data.thread_user_id == current_user.id:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Post authors cannot reply to their own comments.")
    thread_id = comment_data.thread_user_id
  else:
    thread_id = current_user.id
  now = datetime.now(timezone.utc)
  new_comment_doc = {
    "post_id": post["_id"], "post_author_id": post["author_id"], "commenter_id": current_user.id,
    "commenter_username": current_user.username, "content": comment_data.content,
    "created_at": now, "thread_user_id": thread_id
  }
  result = comments_collection.insert_one(new_comment_doc)
  posts_collection.update_one({"_id": post["_id"]}, {"$inc": {"comment_count": 1}, "$pull": {"seen_by_details": {"user_id": post["author_id"]}}})
  
  other_member_ids = [
    member['user_id'] for member in circle.get('members', [])
    if member['user_id'] != current_user.id
  ]
  if other_member_ids:
    activity_event = {
      "circle_id": circle["_id"],
      "post_id": post["_id"],
      "actor_id": current_user.id,
      "actor_username": current_user.username,
      "event_type": ActivityEventTypeEnum.new_comment,
      "timestamp": now,
      "notified_user_ids": other_member_ids
    }
    activity_events_collection.insert_one(activity_event)

  created_comment = await get_comment_or_404(str(result.inserted_id))

  if not is_author:
    await create_notification(
      user_id=post["author_id"],
      notification_type=NotificationTypeEnum.new_comment,
      content={
        "circle_id": str(circle["_id"]),
        "circle_name": circle["name"],
        "post_id": str(post["_id"]),
        "commenter_username": current_user.username
      }
    )

  return CommentOut(**created_comment)

@app.get("/posts/{post_id}/commenters", response_model=List[CommenterInfo], tags=["Comments"])
async def get_post_commenters(post_id: str, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if current_user.id != post["author_id"]:
    raise HTTPException(status_code=403, detail="Only the post author can view the list of commenters.")
  last_seen_time = next((item['seen_at'] for item in post.get('seen_by_details', []) if item['user_id'] == current_user.id), None)
  pipeline = [
    {"$match": {"post_id": post["_id"]}},
    {"$sort": {"created_at": -1}},
    {"$group": {"_id": "$thread_user_id", "username": {"$first": "$commenter_username"}, "comment_count": {"$sum": 1}, "latest_comment_time": {"$max": "$created_at"}}},
    {"$project": {
      "_id": 0, "user_id": "$_id", "username": "$username", "comment_count": "$comment_count",
      "has_unread": {
        "$cond": {
          "if": {"$and": [{"$ne": ["$_id", current_user.id]}, {"$ne": [last_seen_time, None]}, {"$gt": ["$latest_comment_time", last_seen_time]}]},
          "then": True,
          "else": {"$cond": {"if": {"$and": [{"$ne": ["$_id", current_user.id]}, {"$eq": [last_seen_time, None]}]}, "then": True, "else": False}}
        }
      }
    }},
    {"$sort": {"has_unread": -1, "username": 1}}
  ]
  commenters = list(comments_collection.aggregate(pipeline))
  return [CommenterInfo(**c) for c in commenters]

@app.get("/posts/{post_id}/comments", response_model=List[CommentOut], tags=["Comments"])
async def get_comments_for_post(post_id: str, thread_user_id: Optional[str] = Query(None), current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  circle = await get_circle_or_404(str(post["circle_id"]))
  await check_circle_membership(current_user, circle)
  query = {"post_id": post["_id"]}
  is_author = (current_user.id == post["author_id"])
  if is_author:
    if not thread_user_id or not ObjectId.is_valid(thread_user_id):
      raise HTTPException(status_code=400, detail="Post author must specify a valid thread_user_id to view comments.")
    query["thread_user_id"] = ObjectId(thread_user_id)
  else:
    query["thread_user_id"] = current_user.id
  comments_cursor = comments_collection.find(query).sort("created_at", ASCENDING)
  return [CommentOut(**comment) for comment in comments_cursor]

@app.delete("/comments/{comment_id}", status_code=204, tags=["Comments"])
async def delete_comment(comment_id: str, current_user: UserInDB = Depends(get_current_user)):
  comment = await get_comment_or_404(comment_id)
  if comment["commenter_id"] != current_user.id:
    raise HTTPException(status_code=403, detail="You can only delete your own comments.")
  delete_result = comments_collection.delete_one({"_id": comment["_id"]})
  if delete_result.deleted_count > 0:
    posts_collection.update_one({"_id": comment["post_id"]}, {"$inc": {"comment_count": -1}})
  return Response(status_code=204)

@app.get("/feed", response_model=FeedResponse, tags=["Feeds"])
async def get_my_feed(
  current_user: UserInDB = Depends(get_current_user), skip: int = Query(0, ge=0),
  limit: int = Query(10, ge=1, le=50), circle_id: Optional[str] = None,
  sort_by: SortByEnum = SortByEnum.newest, tags: Optional[str] = None
):
  user_circles_cursor = circles_collection.find({"members.user_id": current_user.id}, {"_id": 1, "name": 1})
  user_circles = {c["_id"]: c["name"] for c in user_circles_cursor}
  if not user_circles:
    return FeedResponse(posts=[], has_more=False)
  match_query = {}
  if circle_id:
    if not ObjectId.is_valid(circle_id) or ObjectId(circle_id) not in user_circles:
      raise HTTPException(status_code=403, detail="Cannot filter by a circle you are not a member of.")
    match_query["circle_id"] = ObjectId(circle_id)
  else:
    match_query["circle_id"] = {"$in": list(user_circles.keys())}
  if tags:
    tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
    if tag_list:
      match_query["content.tags"] = {"$all": tag_list}
  match_stage = {"$match": match_query}
  total_posts = posts_collection.count_documents(match_query)
  sort_stage = {"$sort": {"created_at": DESCENDING}}
  pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
  cursor = posts_collection.aggregate(pipeline)
  posts_list = []
  for p in cursor:
    posts_list.append(PostOut(**p, circle_name=user_circles.get(p["circle_id"], "Unknown")))
  return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)

# ----------------------------------
# Chat
# ----------------------------------
@app.get("/posts/{post_id}/chat", response_model=List[ChatMessageOut], tags=["Chat"])
async def get_chat_messages(post_id: str, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if not post.get("is_chat_enabled"):
    raise HTTPException(status_code=404, detail="Chat is not enabled for this post.")
  
  participant_ids = [p['user_id'] for p in post.get("chat_participants", [])]
  if current_user.id not in participant_ids:
    raise HTTPException(status_code=403, detail="You are not a participant in this chat.")
    
  messages = post.get("chat_messages", [])
  return [ChatMessageOut(id=msg["_id"], **msg) for msg in messages]

@app.post("/posts/{post_id}/chat", response_model=ChatMessageOut, status_code=201, tags=["Chat"])
async def post_chat_message(post_id: str, message_data: ChatMessageCreate, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if not post.get("is_chat_enabled"):
    raise HTTPException(status_code=404, detail="Chat is not enabled for this post.")
  
  participants = post.get("chat_participants", [])
  participant_ids = [p['user_id'] for p in participants]
  if current_user.id not in participant_ids:
    raise HTTPException(status_code=403, detail="You are not a participant in this chat.")

  new_message_doc = {
    "_id": ObjectId(),
    "sender_id": current_user.id,
    "sender_username": current_user.username,
    "content": message_data.content,
    "timestamp": datetime.now(timezone.utc)
  }
  
  posts_collection.update_one(
    {"_id": post["_id"]},
    {"$push": {"chat_messages": new_message_doc}}
  )
  
  return ChatMessageOut(id=new_message_doc["_id"], **new_message_doc)

@app.get("/posts/{post_id}/chat/participants", response_model=List[ChatParticipant], tags=["Chat"])
async def get_chat_participants(post_id: str, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if not post.get("is_chat_enabled"):
    raise HTTPException(status_code=404, detail="Chat is not enabled for this post.")
  
  participants = post.get("chat_participants", [])
  participant_ids = [p['user_id'] for p in participants]
  if current_user.id not in participant_ids:
    raise HTTPException(status_code=403, detail="You are not a participant in this chat.")
    
  return [ChatParticipant(**p) for p in participants]

@app.put("/posts/{post_id}/chat/participants", response_model=List[ChatParticipant], tags=["Chat"])
async def update_chat_participants(post_id: str, update_data: ChatParticipantUpdateRequest, current_user: UserInDB = Depends(get_current_user)):
  post = await get_post_or_404(post_id)
  if post["author_id"] != current_user.id:
    raise HTTPException(status_code=403, detail="Only the post author can manage chat participants.")
  
  # Ensure the author is always included
  participant_id_set = set(update_data.participant_ids)
  participant_id_set.add(post["author_id"])
  
  new_participant_ids = list(participant_id_set)

  # Fetch usernames for the new list of participants
  new_participants_cursor = users_collection.find(
    {"_id": {"$in": new_participant_ids}},
    {"_id": 1, "username": 1}
  )
  new_participant_docs = [{"user_id": p["_id"], "username": p["username"]} for p in await new_participants_cursor.to_list(length=None)]

  posts_collection.update_one(
    {"_id": post["_id"]},
    {"$set": {"chat_participants": new_participant_docs}}
  )
  
  return [ChatParticipant(**p) for p in new_participant_docs]

# ----------------------------------
# Static / Frontend
# ----------------------------------
app.mount("/ux", StaticFiles(directory="ux", html=True), name="ux")
@app.get("/", include_in_schema=False)
async def serve_frontend_entrypoint():
  # Ensure the ux directory and index.html exist
  if os.path.isdir("ux") and os.path.isfile("ux/index.html"):
      return FileResponse("ux/index.html")
  return Response(content="Frontend not found.", status_code=404)

if __name__ == "__main__":
  print("Starting server on http://127.0.0.1:8000")
  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)