# ==============================================================================
# Circles Social API (FastAPI backend)
# main.py
# ==============================================================================

import os
import re
import secrets
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union, Callable
from contextlib import asynccontextmanager
from enum import Enum
from urllib.parse import urlparse

import uvicorn
import jwt
import requests
from bs4 import BeautifulSoup
from jwt.exceptions import PyJWTError
from fastapi import FastAPI, HTTPException, Body, Depends, status, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, AnyHttpUrl
from passlib.context import CryptContext
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from bson import ObjectId
from pydantic_core import core_schema
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ==============================================================================
# 1. CONFIGURATION & INITIALIZATION
# ==============================================================================

# Security & JWT
SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key-that-you-should-change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
INVITE_TOKEN_EXPIRE_HOURS = 24

# Cloudinary Configuration
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
    print("Warning: Cloudinary credentials not found in environment variables. Image uploads will be disabled.")


# MongoDB
MONGO_DETAILS = os.getenv("MONGO_URI", "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true")
client = MongoClient(MONGO_DETAILS)
db = client.circles_app

users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
events_collection = db.get_collection("events")
invite_tokens_collection = db.get_collection("invite_tokens")
chat_messages_collection = db.get_collection("chat_messages")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure indexes exist
    users_collection.create_index([("username", ASCENDING)], unique=True)
    circles_collection.create_index([("name", ASCENDING)])
    posts_collection.create_index([("circle_id", ASCENDING)])
    posts_collection.create_index([("created_at", DESCENDING)])
    posts_collection.create_index([("score", DESCENDING), ("created_at", DESCENDING)])
    posts_collection.create_index([("is_pinned", DESCENDING), ("created_at", DESCENDING)])
    posts_collection.create_index([("content.tags", ASCENDING)])
    events_collection.create_index([("circle_id", ASCENDING), ("start_time", DESCENDING)])
    invite_tokens_collection.create_indexes([IndexModel([("expires_at", DESCENDING)], expireAfterSeconds=0)])
    chat_messages_collection.create_index([("circle_id", ASCENDING), ("timestamp", DESCENDING)])
    print("Database indexes ensured.")
    yield
    client.close()


app = FastAPI(
    title="Circles Social API",
    description="A complete API with user auth, circles, posts, events, and real-time chat/video.",
    version="6.0.0",
    lifespan=lifespan,
)

# FIX: Allow all origins for development to resolve CORS issues.
# For production, you should restrict this to your actual frontend domain.
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PermissionsPolicyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        response = await call_next(request)
        response.headers['Permissions-Policy'] = 'compute-pressure=(self "https://www.youtube.com")'
        return response

app.add_middleware(PermissionsPolicyMiddleware)

# ==============================================================================
# 2. Pydantic MODELS
# ==============================================================================


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: Any
    ) -> core_schema.CoreSchema:
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


class SortByEnum(str, Enum):
    newest = "newest"
    top = "top"


class PostTypeEnum(str, Enum):
    standard = "standard"
    yt_playlist = "yt-playlist"
    poll = "poll"
    wishlist = "wishlist"
    image = "image"


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class UserAuth(BaseModel):
    username: str
    password: str


class UserInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    username: str
    password_hash: str

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True


class UserOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    username: str

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True

class UserMeOut(UserOut):
    # This model can be expanded later if more private user fields are added
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

    class Config:
        json_encoders = {ObjectId: str}


class CircleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_public: bool = True
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class CircleUpdate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_public: bool = True
    password: Optional[str] = Field(None, min_length=8, max_length=128, description="Provide a new password to change it, or null/blank to remove it.")


class CircleJoin(BaseModel):
    password: str


class CircleStatusOut(BaseModel):
    name: str
    is_password_protected: bool


class CircleOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    description: Optional[str]
    is_public: bool
    owner_id: PyObjectId
    member_count: int
    is_password_protected: bool
    user_role: Optional[RoleEnum] = None

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True

class CircleManagementOut(CircleOut):
    members: List[CircleMember] = []

class MemberRoleUpdate(BaseModel):
    role: RoleEnum

class InviteTokenCreateResponse(BaseModel):
    token: str
    expires_at: datetime


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


class WishlistData(BaseModel):
    url: AnyHttpUrl
    title: str
    description: Optional[str] = None
    image: Optional[AnyHttpUrl] = None


class PostCreate(BaseModel):
    post_type: PostTypeEnum = PostTypeEnum.standard
    text: Optional[str] = Field(None, max_length=10000)
    link: Optional[str] = Field(None)
    tags: list[str] = Field(default_factory=list)
    playlist_data: Optional[PlaylistData] = None
    poll_data: Optional[PollData] = None
    wishlist_data: Optional[WishlistData] = None
    image_data: Optional[ImageData] = None

    def model_validate(self):
        if self.post_type == PostTypeEnum.standard and not self.text and not self.link:
            raise ValueError('A standard post must contain either text or a link.')
        if self.post_type == PostTypeEnum.yt_playlist:
            if not self.playlist_data or not self.playlist_data.name or not self.playlist_data.videos:
                raise ValueError('A YouTube playlist post must contain a name and at least one video.')
        if self.post_type == PostTypeEnum.poll and not self.poll_data:
            raise ValueError('A poll post must contain poll_data.')
        if self.post_type == PostTypeEnum.wishlist and not self.wishlist_data:
            raise ValueError('A wishlist post must contain wishlist_data.')
        # Allow an image post if it has image_data OR a link to be processed
        if self.post_type == PostTypeEnum.image and not self.image_data and not self.link:
            raise ValueError('An image post must contain image_data from an upload or a direct link.')
        self.tags = sorted(set(tag.strip().lower() for tag in self.tags if tag.strip()))
        return self


class PostOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    circle_id: PyObjectId
    circle_name: str
    author_id: PyObjectId
    author_username: str
    content: dict[str, Any]
    created_at: datetime
    score: int = 0
    is_pinned: bool = False
    upvotes_count: int = 0
    downvotes_count: int = 0
    user_vote: int = 0
    poll_results: Optional[dict] = None

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True


class FeedResponse(BaseModel):
    posts: list[PostOut]
    has_more: bool


class VoteRequest(BaseModel):
    direction: int


class PollVoteRequest(BaseModel):
    option_index: int


class MetadataResponse(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None


class EventCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=200)

class EventOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    circle_id: PyObjectId
    creator_id: PyObjectId
    creator_username: str
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    location: Optional[str]
    attendee_count: int = 0
    is_attending: bool = False

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True

class RsvpResponse(BaseModel):
    attendee_count: int

# ==============================================================================
# 3. HELPER & DEPENDENCY FUNCTIONS
# ==============================================================================


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


async def get_current_user_from_token(token: str) -> Optional[UserInDB]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access":
            return None
        username = payload.get("sub")
        if not username:
            return None
        user_doc = users_collection.find_one({"username": username})
        return UserInDB(**user_doc) if user_doc else None
    except (PyJWTError, ValueError):
        return None


async def get_optional_current_user(request: Request) -> Optional[UserInDB]:
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


async def get_circle_or_404(circle_id: str) -> dict:
    if not ObjectId.is_valid(circle_id):
        raise HTTPException(status_code=400, detail="Invalid Circle ID")
    circle = circles_collection.find_one({"_id": ObjectId(circle_id)})
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    return circle


async def get_post_or_404(post_id: str) -> dict:
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid Post ID")
    post = posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


async def get_event_or_404(event_id: str) -> dict:
    if not ObjectId.is_valid(event_id):
        raise HTTPException(status_code=400, detail="Invalid Event ID")
    event = events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


async def check_circle_membership(current_user: UserInDB = Depends(get_current_user), circle: dict = Depends(get_circle_or_404)) -> dict:
    if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
        if not circle["is_public"] or ("password_hash" in circle and circle["password_hash"]):
            raise HTTPException(status_code=403, detail="You are not a member of this circle.")
    return circle


async def get_circle_and_user_role(circle_id: str, current_user: UserInDB = Depends(get_current_user)) -> tuple[dict, RoleEnum]:
    circle = await get_circle_or_404(circle_id)
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    if not member_info:
        raise HTTPException(status_code=403, detail="You are not a member of this circle.")
    return circle, RoleEnum(member_info['role'])


def _get_posts_aggregation_pipeline(
    match_stage: dict,
    sort_stage: dict,
    skip: int,
    limit: int,
    current_user: Optional[UserInDB]
) -> list[dict]:
    pipeline = [match_stage]

    add_fields_stage = {
        "$addFields": {
            "upvotes_count": {"$size": {"$ifNull": ["$upvotes", []]}},
            "downvotes_count": {"$size": {"$ifNull": ["$downvotes", []]}},
        }
    }
    pipeline.append(add_fields_stage)
    pipeline.append({"$addFields": {
        "score": {"$subtract": ["$upvotes_count", "$downvotes_count"]}
    }})

    if current_user:
        pipeline.append({
            "$addFields": {
                "user_vote": {
                    "$cond": {
                        "if": {"$in": [current_user.id, {"$ifNull": ["$upvotes", []]}]},
                        "then": 1,
                        "else": {
                            "$cond": {
                                "if": {"$in": [current_user.id, {"$ifNull": ["$downvotes", []]}]},
                                "then": -1,
                                "else": 0
                            }
                        }
                    }
                },
                "poll_results": {
                    "$cond": {
                        "if": {"$eq": ["$content.post_type", "poll"]},
                        "then": {
                            "total_votes": {
                                "$reduce": {
                                    "input": "$content.poll_data.options",
                                    "initialValue": 0,
                                    "in": {
                                        "$add": [
                                            "$$value",
                                            {"$size": {"$ifNull": ["$$this.votes", []]}}
                                        ]
                                    }
                                }
                            },
                            "options": {
                                "$map": {
                                    "input": "$content.poll_data.options",
                                    "as": "option",
                                    "in": {
                                        "text": "$$option.text",
                                        "votes": {"$size": {"$ifNull": ["$$option.votes", []]}}
                                    }
                                }
                            },
                            "user_voted_index": {
                                "$indexOfArray": [
                                    {
                                        "$map": {
                                            "input": "$content.poll_data.options",
                                            "as": "option",
                                            "in": {
                                                "$in": [current_user.id, {"$ifNull": ["$$option.votes", []]}]
                                            }
                                        }
                                    },
                                    True
                                ]
                            }
                        },
                        "else": "$$REMOVE"
                    }
                }
            }
        })

    pipeline.extend([
        sort_stage,
        {"$skip": skip},
        {"$limit": limit}
    ])
    return pipeline

# ==============================================================================
# 4. WEBSOCKET & CHAT MANAGER
# ==============================================================================


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, circle_id: str, user: UserInDB):
        await websocket.accept()
        if circle_id not in self.active_connections:
            self.active_connections[circle_id] = {}
        join_msg = {"type": "user-joined", "user_id": str(user.id), "username": user.username}
        await self.broadcast(json.dumps(join_msg), circle_id, exclude=websocket)
        user_list = [
            {"user_id": uid, "username": ws.scope["user"].username}
            for uid, ws in self.active_connections[circle_id].items()
        ]
        await websocket.send_json({"type": "existing-users", "users": user_list})
        history_cursor = chat_messages_collection.find({"circle_id": ObjectId(circle_id)}) \
            .sort("timestamp", DESCENDING).limit(50)

        def serialize_history(doc):
            doc['_id'] = str(doc['_id'])
            doc['circle_id'] = str(doc['circle_id'])
            doc['sender_id'] = str(doc['sender_id'])
            doc['timestamp'] = doc['timestamp'].isoformat()
            return doc
        history = [serialize_history(msg) for msg in history_cursor]
        history.reverse()
        await websocket.send_json({"type": "chat-history", "history": history})

        self.active_connections[circle_id][str(user.id)] = websocket
        websocket.scope["user"] = user

    def disconnect(self, websocket: WebSocket, circle_id: str, user_id: str):
        if circle_id in self.active_connections and user_id in self.active_connections[circle_id]:
            del self.active_connections[circle_id][user_id]
            if not self.active_connections[circle_id]:
                del self.active_connections[circle_id]

    async def broadcast(self, message: str, circle_id: str, exclude: Optional[WebSocket] = None):
        if circle_id in self.active_connections:
            for conn in self.active_connections[circle_id].values():
                if conn != exclude:
                    await conn.send_text(message)

    async def send_personal_message(self, message: str, user_id: str, circle_id: str):
        if circle_id in self.active_connections and user_id in self.active_connections[circle_id]:
            await self.active_connections[circle_id][user_id].send_text(message)


manager = ConnectionManager()


@app.websocket("/ws/chat/{circle_id}")
async def websocket_endpoint(websocket: WebSocket, circle_id: str, token: str = Query(...)):
    user = await get_current_user_from_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    circle = await get_circle_or_404(circle_id)
    if not any(m['user_id'] == user.id for m in circle.get('members', [])):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = str(user.id)
    await manager.connect(websocket, circle_id, user)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            if msg_type in ["offer", "answer", "candidate"]:
                recipient_id = message.get("to")
                message["from"] = user_id
                await manager.send_personal_message(json.dumps(message), recipient_id, circle_id)
            elif msg_type == "media-state":
                message["from"] = user_id
                await manager.broadcast(json.dumps(message), circle_id, exclude=websocket)
            elif msg_type == "chat":
                chat_messages_collection.insert_one({
                    "circle_id": ObjectId(circle_id), "sender_id": user.id, "sender_username": user.username,
                    "content": message.get("content", ""), "timestamp": datetime.now(timezone.utc)
                })
                broadcast_msg = {
                    "type": "chat", "sender_id": user_id, "sender_username": user.username,
                    "content": message.get("content", ""), "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await manager.broadcast(json.dumps(broadcast_msg), circle_id)
            else:
                message["from"] = user_id
                await manager.broadcast(json.dumps(message), circle_id, exclude=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, circle_id, user_id)
        leave_msg = json.dumps({"type": "user-left", "user_id": user_id})
        await manager.broadcast(leave_msg, circle_id)

# ==============================================================================
# 5. API ENDPOINTS
# ==============================================================================

# -- Utilities --

@app.get("/utils/cloudinary-signature", tags=["Utilities"])
async def get_cloudinary_signature(current_user: UserInDB = Depends(get_current_user)):
    """Provides a signature for direct-from-browser uploads to Cloudinary."""
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        raise HTTPException(status_code=503, detail="Cloudinary service is not configured on the server.")
    
    timestamp = int(time.time())
    params_to_sign = {"timestamp": timestamp}
    
    signature = cloudinary.utils.api_sign_request(params_to_sign, CLOUDINARY_API_SECRET)
    
    return {
        "signature": signature,
        "timestamp": timestamp,
        "api_key": CLOUDINARY_API_KEY,
        "cloud_name": CLOUDINARY_CLOUD_NAME
    }


@app.get("/utils/extract-metadata", response_model=MetadataResponse, tags=["Utilities"])
async def extract_metadata(url: AnyHttpUrl, current_user: UserInDB = Depends(get_current_user)):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(str(url), headers=headers, timeout=5, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        title = soup.find("meta", property="og:title") or soup.find("title")
        description = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        image = soup.find("meta", property="og:image")
        return MetadataResponse(
            url=str(url),
            title=title.get("content", title.text) if title else "No title found",
            description=description.get("content") if description else "No description available.",
            image=image.get("content") if image else None
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")

# -- AUTH --


@app.post("/auth/register", response_model=UserOut, status_code=201, tags=["Authentication"])
async def register_user(user_data: UserRegister):
    if users_collection.find_one({"username": user_data.username}):
        raise HTTPException(status_code=400, detail="Username already registered")
    new_user_doc = {
        "username": user_data.username, 
        "password_hash": pwd_context.hash(user_data.password)
    }
    result = users_collection.insert_one(new_user_doc)
    created_user = users_collection.find_one({"_id": result.inserted_id})
    return UserOut(**created_user)


@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login_for_access_token(form_data: UserAuth):
    user = users_collection.find_one({"username": form_data.username})
    if not user or not pwd_context.verify(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(user["username"])
    refresh_token = create_refresh_token(user["username"])
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
async def refresh_access_token(body: TokenRefreshRequest):
    credentials_exception = HTTPException(
        status_code=401, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh": raise credentials_exception
        username = payload.get("sub")
        if not username: raise credentials_exception
    except PyJWTError:
        raise credentials_exception
    user_doc = users_collection.find_one({"username": username})
    if not user_doc: raise credentials_exception
    new_access_token = create_access_token(username)
    new_refresh_token = create_refresh_token(username)
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)

# -- User --


@app.get("/users/me", response_model=UserMeOut, tags=["Users"])
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    # FIX: Use by_alias=True to ensure the dictionary key is "_id" for validation.
    return UserMeOut(**current_user.dict(by_alias=True))

# -- Circles --


@app.get("/circles/mine", response_model=List[CircleOut], tags=["Circles"])
async def list_my_circles(current_user: UserInDB = Depends(get_current_user)):
    circles_cursor = circles_collection.find({"members.user_id": current_user.id}).sort("name", ASCENDING)
    result = []
    for c in circles_cursor:
        is_protected = "password_hash" in c and c.get("password_hash") is not None
        item = CircleOut(
            **c, member_count=len(c.get("members", [])),
            is_password_protected=is_protected, user_role=None
        )
        result.append(item)
    return result


@app.post("/circles", response_model=CircleOut, status_code=201, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
    first_member = CircleMember(
        user_id=current_user.id, username=current_user.username, role=RoleEnum.admin
    )
    new_circle_doc = {
        "name": circle_data.name, "description": circle_data.description, "is_public": circle_data.is_public,
        "owner_id": current_user.id, "members": [first_member.dict()], "created_at": datetime.now(timezone.utc)
    }
    if circle_data.password:
        new_circle_doc["password_hash"] = pwd_context.hash(circle_data.password)
    result = circles_collection.insert_one(new_circle_doc)
    created_circle = circles_collection.find_one({"_id": result.inserted_id})
    is_protected = "password_hash" in created_circle and created_circle.get("password_hash") is not None
    return CircleOut(
        **created_circle, member_count=1, is_password_protected=is_protected, user_role=RoleEnum.admin
    )


@app.get("/circles/{circle_id}/status", response_model=CircleStatusOut, tags=["Circles"])
async def get_circle_public_status(circle: dict = Depends(get_circle_or_404)):
    is_protected = "password_hash" in circle and circle.get("password_hash") is not None
    return CircleStatusOut(name=circle["name"], is_password_protected=is_protected)


@app.post("/circles/{circle_id}/join", status_code=204, tags=["Circles"])
async def join_password_protected_circle(
    join_data: CircleJoin, circle: dict = Depends(get_circle_or_404), current_user: UserInDB = Depends(get_current_user)
):
    if not circle.get("password_hash"):
        raise HTTPException(status_code=400, detail="This circle is not password protected.")
    if any(m['user_id'] == current_user.id for m in circle.get("members", [])): return
    if not pwd_context.verify(join_data.password, circle["password_hash"]):
        raise HTTPException(status_code=403, detail="Incorrect password")
    new_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.member)
    circles_collection.update_one({"_id": circle["_id"]}, {"$addToSet": {"members": new_member.dict()}})


@app.post("/circles/{circle_id}/invite-token", response_model=InviteTokenCreateResponse, tags=["Circles"])
async def create_invite_token(circle: dict = Depends(check_circle_membership)):
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_TOKEN_EXPIRE_HOURS)
    invite_tokens_collection.insert_one({"token": token, "circle_id": circle["_id"], "expires_at": expires_at})
    return InviteTokenCreateResponse(token=token, expires_at=expires_at)


@app.post("/circles/join-by-token", response_model=JoinByTokenResponse, tags=["Circles"])
async def join_circle_by_token(body: JoinByTokenRequest, current_user: UserInDB = Depends(get_current_user)):
    token_doc = invite_tokens_collection.find_one({
        "token": body.token, "expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    if not token_doc: raise HTTPException(status_code=400, detail="Invite link is invalid or has expired.")
    circle = circles_collection.find_one({"_id": token_doc["circle_id"]})
    if not circle:
        raise HTTPException(status_code=404, detail="The circle associated with this invite no longer exists.")
    if any(m['user_id'] == current_user.id for m in circle.get("members", [])):
        return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])
    new_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.member)
    circles_collection.update_one({"_id": circle["_id"]}, {"$addToSet": {"members": new_member.dict()}})
    return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])


@app.get("/circles/{circle_id}", response_model=Union[CircleManagementOut, CircleOut], tags=["Circles"])
async def get_circle_details(circle_id: str, current_user: UserInDB = Depends(get_current_user)):
    circle = await get_circle_or_404(circle_id)
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    user_role = RoleEnum(member_info['role']) if member_info else None

    if not user_role and (not circle["is_public"] or circle.get("password_hash")):
        raise HTTPException(status_code=403, detail="You do not have access to this circle.")

    is_protected = "password_hash" in circle and circle.get("password_hash") is not None
    member_count = len(circle.get("members", []))

    if user_role in [RoleEnum.admin, RoleEnum.moderator]:
        circle_data = circle.copy()
        raw_members = circle_data.pop("members", [])

        return CircleManagementOut(
            **circle_data,
            member_count=member_count,
            is_password_protected=is_protected,
            user_role=user_role,
            members=[CircleMember(**m) for m in raw_members]
        )
    else:
        return CircleOut(
            **circle,
            member_count=member_count,
            is_password_protected=is_protected,
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
    if circle_data.password:
        update_doc["password_hash"] = pwd_context.hash(circle_data.password)
    elif "password" in circle_data.model_dump(exclude_unset=True):
        update_doc["password_hash"] = None

    circles_collection.update_one(
        {"_id": circle["_id"]},
        {"$set": update_doc}
    )
    updated_circle = await get_circle_or_404(circle_id)
    return await get_circle_details(circle_id, current_user)


@app.delete("/circles/{circle_id}", status_code=204, tags=["Circles"])
async def delete_circle(circle_id: str, current_user: UserInDB = Depends(get_current_user)):
    circle, user_role = await get_circle_and_user_role(circle_id, current_user)
    if user_role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only circle admins can delete the circle.")
    
    posts_collection.delete_many({"circle_id": circle["_id"]})
    circles_collection.delete_one({"_id": circle["_id"]})
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
        if target_member["role"] in [RoleEnum.admin, RoleEnum.moderator] or role_data.role in [RoleEnum.admin, RoleEnum.moderator]:
            raise HTTPException(status_code=403, detail="Moderators can only manage members.")
    else:
        raise HTTPException(status_code=403, detail="You do not have permission to manage roles.")

    circles_collection.update_one(
        {"_id": circle["_id"], "members.user_id": target_user_id},
        {"$set": {"members.$.role": role_data.role.value}}
    )
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
    if user_role == RoleEnum.admin:
        pass
    elif user_role == RoleEnum.moderator:
        if target_member["role"] in [RoleEnum.admin, RoleEnum.moderator]:
            raise HTTPException(status_code=403, detail="Moderators can only kick members.")
    else:
        raise HTTPException(status_code=403, detail="You do not have permission to kick members.")

    circles_collection.update_one(
        {"_id": circle["_id"]},
        {"$pull": {"members": {"user_id": target_user_id}}}
    )
    return await get_circle_details(circle_id, current_user)

# -- Feeds & Posts --


@app.get("/circles/{circle_id}/feed", response_model=FeedResponse, tags=["Feeds"])
async def get_circle_feed(
    circle_id: str, skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50),
    sort_by: SortByEnum = Query(SortByEnum.newest), tags: Optional[str] = None,
    current_user: Optional[UserInDB] = Depends(get_optional_current_user)
):
    circle = await get_circle_or_404(circle_id)
    is_member = current_user and any(m['user_id'] == current_user.id for m in circle.get('members', []))
    if not circle["is_public"] and not is_member:
        if circle.get("password_hash"):
            raise HTTPException(status_code=401, detail="This circle is password protected. Please join to view.")
        raise HTTPException(status_code=403, detail="You must be a member to view this circle's feed.")
    match_query = {"circle_id": circle["_id"]}
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(',') if t.strip()]
        if tag_list: match_query["content.tags"] = {"$all": tag_list}
    match_stage = {"$match": match_query}
    total_posts = posts_collection.count_documents(match_query)
    sort_logic = {"score": DESCENDING, "created_at": DESCENDING} if sort_by == SortByEnum.top else {"created_at": DESCENDING}
    sort_stage = {"$sort": {"is_pinned": DESCENDING, **sort_logic}}
    pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
    cursor = posts_collection.aggregate(pipeline)
    posts_list = [PostOut(**p, circle_name=circle["name"]) for p in cursor]
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)


@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=201, tags=["Posts"])
async def create_post_in_circle(
    post_data: PostCreate, circle: dict = Depends(check_circle_membership),
    current_user: UserInDB = Depends(get_current_user)
):
    # Centralized logic to handle image URL uploads for both 'standard' and 'image' post types.
    is_standard_post_with_image_link = (
        post_data.post_type == PostTypeEnum.standard and
        post_data.link and
        re.search(r'\.(jpg|jpeg|png|gif|webp)$', post_data.link.lower())
    )
    is_image_post_with_link = (
        post_data.post_type == PostTypeEnum.image and
        post_data.link and not post_data.image_data
    )

    if is_standard_post_with_image_link or is_image_post_with_link:
        if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
            try:
                # Upload the image to Cloudinary from the provided URL
                upload_result = cloudinary.uploader.upload(post_data.link)
                # Convert the post to a proper image post
                post_data.post_type = PostTypeEnum.image
                post_data.image_data = ImageData(
                    url=upload_result.get("secure_url"),
                    public_id=upload_result.get("public_id"),
                    height=upload_result.get("height"),
                    width=upload_result.get("width")
                )
                # Clear the link as it's now stored in image_data
                post_data.link = None
            except Exception as e:
                # If upload fails, proceed as a standard post with a link
                print(f"Cloudinary auto-upload failed: {e}")
                post_data.post_type = PostTypeEnum.standard

    post_data.model_validate()
    content_data = jsonable_encoder(post_data.dict(exclude_unset=True))
    new_post_doc = {
        "circle_id": circle["_id"], "author_id": current_user.id, "author_username": current_user.username,
        "content": content_data, "created_at": datetime.now(timezone.utc),
        "upvotes": [], "downvotes": [], "score": 0, "is_pinned": False
    }
    if post_data.post_type == PostTypeEnum.poll and post_data.poll_data:
        for option in new_post_doc["content"]["poll_data"]["options"]: option["votes"] = []
    result = posts_collection.insert_one(new_post_doc)
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    return PostOut(**created_post, circle_name=circle["name"])


@app.post("/posts/{post_id}/vote", tags=["Posts"])
async def vote_on_post(post_id: str, vote_data: VoteRequest, current_user: UserInDB = Depends(get_current_user)):
    if not ObjectId.is_valid(post_id): raise HTTPException(status_code=400, detail="Invalid Post ID")
    post_object_id = ObjectId(post_id)
    posts_collection.update_one(
        {"_id": post_object_id}, {"$pull": {"upvotes": current_user.id, "downvotes": current_user.id}}
    )
    direction = vote_data.direction
    if direction not in [-1, 0, 1]: raise HTTPException(status_code=400, detail="Invalid vote direction.")
    if direction != 0:
        field_to_update = "upvotes" if direction == 1 else "downvotes"
        posts_collection.update_one({"_id": post_object_id}, {"$addToSet": {field_to_update: current_user.id}})
    pipeline = [
        {"$match": {"_id": post_object_id}},
        {"$project": {"score": {"$subtract": [
            {"$size": {"$ifNull": ["$upvotes", []]}}, {"$size": {"$ifNull": ["$downvotes", []]}}
        ]}}}
    ]
    result = list(posts_collection.aggregate(pipeline))
    if not result: raise HTTPException(status_code=404, detail="Post not found after voting.")
    new_score = result[0]["score"]
    posts_collection.update_one({"_id": post_object_id}, {"$set": {"score": new_score}})
    return {"status": "success", "new_score": new_score}


@app.post("/posts/{post_id}/poll-vote", tags=["Posts"])
async def vote_on_poll(post_id: str, vote_data: PollVoteRequest, current_user: UserInDB = Depends(get_current_user)):
    post = await get_post_or_404(post_id)
    if post.get("content", {}).get("post_type") != "poll":
        raise HTTPException(status_code=400, detail="This post is not a poll.")
    options = post["content"]["poll_data"]["options"]
    if not (0 <= vote_data.option_index < len(options)):
        raise HTTPException(status_code=400, detail="Invalid poll option index.")
    for i in range(len(options)):
        posts_collection.update_one(
            {"_id": post["_id"]}, {"$pull": {f"content.poll_data.options.{i}.votes": current_user.id}}
        )
    posts_collection.update_one(
        {"_id": post["_id"]},
        {"$addToSet": {f"content.poll_data.options.{vote_data.option_index}.votes": current_user.id}}
    )
    pipeline = _get_posts_aggregation_pipeline({"$match": {"_id": post["_id"]}}, {}, 0, 1, current_user)
    updated_post = list(posts_collection.aggregate(pipeline))
    if not updated_post: raise HTTPException(status_code=404, detail="Post not found after poll vote.")
    return {"status": "success", "poll_results": updated_post[0]["poll_results"]}


@app.post("/posts/{post_id}/pin", tags=["Posts"])
async def toggle_pin_post(post_id: str, current_user: UserInDB = Depends(get_current_user)):
    post_doc = await get_post_or_404(post_id)
    circle, user_role = await get_circle_and_user_role(str(post_doc["circle_id"]), current_user)
    if user_role not in [RoleEnum.admin, RoleEnum.moderator]:
        raise HTTPException(status_code=403, detail="You do not have permission to pin posts in this circle.")
    new_pinned_state = not post_doc.get("is_pinned", False)
    posts_collection.update_one({"_id": post_doc["_id"]}, {"$set": {"is_pinned": new_pinned_state}})
    return {"status": "success", "is_pinned": new_pinned_state}


@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=204, tags=["Posts"])
async def delete_post(
    circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user),
    circle: dict = Depends(get_circle_or_404)
):
    if not ObjectId.is_valid(post_id): raise HTTPException(status_code=400, detail="Invalid Post ID")
    post = posts_collection.find_one({"_id": ObjectId(post_id), "circle_id": ObjectId(circle_id)})
    if not post: raise HTTPException(status_code=404, detail="Post not found in this circle")
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    user_is_mod_or_admin = member_info and RoleEnum(member_info['role']) in [RoleEnum.moderator, RoleEnum.admin]
    if not (post['author_id'] == current_user.id or user_is_mod_or_admin):
        raise HTTPException(status_code=403, detail="You don't have permission to delete this post")
    posts_collection.delete_one({"_id": ObjectId(post_id)})


@app.get("/feed", response_model=FeedResponse, tags=["Feeds"])
async def get_my_feed(
    current_user: UserInDB = Depends(get_current_user), skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50), circle_id: Optional[str] = None,
    sort_by: SortByEnum = SortByEnum.newest, tags: Optional[str] = None
):
    user_circles_cursor = circles_collection.find({"members.user_id": current_user.id}, {"_id": 1, "name": 1})
    user_circles = {c["_id"]: c["name"] for c in user_circles_cursor}
    if not user_circles: return FeedResponse(posts=[], has_more=False)
    match_query = {}
    if circle_id:
        if not ObjectId.is_valid(circle_id) or ObjectId(circle_id) not in user_circles:
            raise HTTPException(status_code=403, detail="Cannot filter by a circle you are not a member of.")
        match_query["circle_id"] = ObjectId(circle_id)
    else:
        match_query["circle_id"] = {"$in": list(user_circles.keys())}
    if tags:
        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_list: match_query["content.tags"] = {"$all": tag_list}
    match_stage = {"$match": match_query}
    total_posts = posts_collection.count_documents(match_query)
    sort_logic = {"score": DESCENDING, "created_at": DESCENDING} if sort_by == SortByEnum.top else {"created_at": DESCENDING}
    sort_stage = {"$sort": {"is_pinned": DESCENDING, **sort_logic}}
    pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
    cursor = posts_collection.aggregate(pipeline)
    posts_list = []
    for p in cursor:
        posts_list.append(PostOut(**p, circle_name=user_circles.get(p["circle_id"], "Unknown")))
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)


# -- Events --

@app.post("/circles/{circle_id}/events", response_model=EventOut, status_code=201, tags=["Events"])
async def create_event_in_circle(
    event_data: EventCreate,
    circle: dict = Depends(check_circle_membership),
    current_user: UserInDB = Depends(get_current_user)
):
    if event_data.end_time and event_data.end_time < event_data.start_time:
        raise HTTPException(status_code=400, detail="End time cannot be before start time.")

    new_event_doc = event_data.dict()
    new_event_doc.update({
        "circle_id": circle["_id"],
        "creator_id": current_user.id,
        "attendees": [],
        "created_at": datetime.now(timezone.utc)
    })
    result = events_collection.insert_one(new_event_doc)
    created_event = await get_event_or_404(str(result.inserted_id))
    return EventOut(
        **created_event,
        creator_username=current_user.username,
        attendee_count=0,
        is_attending=False
    )


@app.get("/circles/{circle_id}/events", response_model=List[EventOut], tags=["Events"])
async def list_events_for_circle(
    circle_id: str,
    upcoming_only: bool = Query(True, alias="upcomingOnly"),
    current_user: UserInDB = Depends(get_current_user)
):
    await check_circle_membership(current_user, await get_circle_or_404(circle_id))
    match_query = {"circle_id": ObjectId(circle_id)}
    if upcoming_only:
        match_query["start_time"] = {"$gte": datetime.now(timezone.utc)}

    pipeline = [
        {"$match": match_query},
        {"$sort": {"start_time": ASCENDING}},
        {"$lookup": {
            "from": "users",
            "localField": "creator_id",
            "foreignField": "_id",
            "as": "creator_info"
        }},
        {"$unwind": "$creator_info"},
        {"$addFields": {
            "creator_username": "$creator_info.username",
            "attendee_count": {"$size": {"$ifNull": ["$attendees", []]}},
            "is_attending": {"$in": [current_user.id, {"$ifNull": ["$attendees", []]}]}
        }},
        {"$project": {"creator_info": 0, "attendees": 0}}
    ]
    events_cursor = events_collection.aggregate(pipeline)
    return [EventOut(**event) for event in events_cursor]


@app.delete("/events/{event_id}", status_code=204, tags=["Events"])
async def delete_event(
    event_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    event = await get_event_or_404(event_id)
    circle, user_role = await get_circle_and_user_role(str(event["circle_id"]), current_user)
    is_creator = event["creator_id"] == current_user.id
    is_privileged = user_role in [RoleEnum.admin, RoleEnum.moderator]
    if not is_creator and not is_privileged:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this event.")
    events_collection.delete_one({"_id": event["_id"]})


@app.post("/events/{event_id}/rsvp", response_model=RsvpResponse, tags=["Events"])
async def rsvp_to_event(
    event_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    event = await get_event_or_404(event_id)
    await check_circle_membership(current_user, await get_circle_or_404(str(event["circle_id"])))
    result = events_collection.update_one(
        {"_id": event["_id"]},
        {"$addToSet": {"attendees": current_user.id}}
    )
    new_count = len(event.get("attendees", []))
    if result.modified_count > 0:
        new_count += 1
    return RsvpResponse(attendee_count=new_count)


@app.delete("/events/{event_id}/rsvp", response_model=RsvpResponse, tags=["Events"])
async def cancel_rsvp_to_event(
    event_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    event = await get_event_or_404(event_id)
    result = events_collection.update_one(
        {"_id": event["_id"]},
        {"$pull": {"attendees": current_user.id}}
    )
    new_count = len(event.get("attendees", []))
    if result.modified_count > 0:
        new_count -= 1
    return RsvpResponse(attendee_count=max(0, new_count))


# ==============================================================================
# 7. SERVER EXECUTION
# ==============================================================================
if __name__ == "__main__":
    print("Starting server on http://127.0.0.1:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

"""
uvicorn main:app --reload
"""

