# ==============================================================================
# 0. IMPORTS
# ==============================================================================
# Standard library imports for OS interaction, time/date handling, and type hinting.
import os
import re
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Any, List, Dict
from contextlib import asynccontextmanager
from enum import Enum

# Third-party library imports.
import uvicorn
import jwt
from jwt.exceptions import PyJWTError
from fastapi import FastAPI, HTTPException, Body, Depends, status, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from passlib.context import CryptContext
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from bson import ObjectId

# ==============================================================================
# 1. CONFIGURATION & INITIALIZATION
# ==============================================================================

# --- Security & JWT Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key-that-you-should-change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
FOLLOW_TOKEN_EXPIRE_MINUTES = 10
INVITE_TOKEN_EXPIRE_HOURS = 24

# --- Database Configuration ---
MONGO_DETAILS = os.getenv("MONGO_URI", "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true")

# --- Global Objects & Instances ---
client = MongoClient(MONGO_DETAILS)
db = client.circles_app
users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
follow_tokens_collection = db.get_collection("follow_tokens")
follow_requests_collection = db.get_collection("follow_requests")
invite_tokens_collection = db.get_collection("invite_tokens")
chat_messages_collection = db.get_collection("chat_messages")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# --- Application Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Connecting to MongoDB...")
    users_collection.create_index([("username", ASCENDING)], unique=True)
    circles_collection.create_index([("name", ASCENDING)])
    posts_collection.create_index([("circle_id", ASCENDING)])
    posts_collection.create_index([("created_at", DESCENDING)])
    posts_collection.create_index([("score", DESCENDING), ("created_at", DESCENDING)])
    posts_collection.create_index([("content.tags", ASCENDING)])
    follow_tokens_collection.create_indexes([IndexModel([("expires_at", DESCENDING)], expireAfterSeconds=0)])
    invite_tokens_collection.create_indexes([IndexModel([("expires_at", DESCENDING)], expireAfterSeconds=0)])
    follow_requests_collection.create_index([("requester_id", ASCENDING)])
    follow_requests_collection.create_index([("recipient_id", ASCENDING)])
    chat_messages_collection.create_index([("circle_id", ASCENDING), ("timestamp", DESCENDING)])
    print("🚀 Database connection established and indexes ensured.")
    yield
    client.close()
    print("🔌 Database connection closed.")

app = FastAPI(
    title="Circles Social API",
    description="A complete API with user auth, circles, posts, and real-time chat/video with persistent history.",
    version="4.0.2",
    lifespan=lifespan,
)

# ==============================================================================
# 2. Pydantic MODELS (Data Schemas)
# ==============================================================================

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls): yield cls.validate
    @classmethod
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v): raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class ChatMessage(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    circle_id: PyObjectId
    sender_id: PyObjectId
    sender_username: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

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
    following: list[PyObjectId] = []
    followers: list[PyObjectId] = []
    class Config: json_encoders = {ObjectId: str}; populate_by_name = True

class UserPublicProfile(BaseModel):
    id: PyObjectId = Field(alias="_id")
    username: str
    following_count: int
    followers_count: int
    class Config: json_encoders = {ObjectId: str}; populate_by_name = True

class FollowRequestOut(BaseModel):
    request_id: PyObjectId = Field(alias="_id")
    requester: UserPublicProfile
    class Config: json_encoders = {ObjectId: str}; populate_by_name = True

class UserPrivateProfile(UserPublicProfile):
    following: list[UserPublicProfile] = []
    incoming_requests: list[FollowRequestOut] = []
    outgoing_requests: list[PyObjectId] = []

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class FollowTokenCreateResponse(BaseModel):
    token: str
    expires_at: datetime

class FollowByTokenRequest(BaseModel):
    token: str

class FollowByTokenResponse(BaseModel):
    followed_username: str

class RespondToRequest(BaseModel):
    action: str

class CircleMember(BaseModel):
    user_id: PyObjectId
    username: str
    role: RoleEnum = RoleEnum.member
    class Config: json_encoders = {ObjectId: str}

class CircleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_public: bool = True
    password: str | None = Field(None, min_length=8, max_length=128)

class CircleJoin(BaseModel):
    password: str

class CircleStatusOut(BaseModel):
    name: str
    is_password_protected: bool

class CircleOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    description: str | None
    is_public: bool
    owner_id: PyObjectId
    member_count: int
    is_password_protected: bool
    class Config: json_encoders = {ObjectId: str}; populate_by_name = True
    
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

class PostCreate(BaseModel):
    post_type: PostTypeEnum = PostTypeEnum.standard
    text: str | None = Field(None, max_length=10000)
    link: str | None = Field(None)
    tags: list[str] = Field(default_factory=list)
    playlist_data: PlaylistData | None = None
    @model_validator(mode='after')
    def check_content_exists(self) -> 'PostCreate':
        if self.post_type == PostTypeEnum.standard and not self.text and not self.link:
            raise ValueError('A standard post must contain either text or a link.')
        if self.post_type == PostTypeEnum.yt_playlist:
            if not self.playlist_data: raise ValueError('A YouTube playlist post must contain playlist data.')
            if not self.playlist_data.name or not self.playlist_data.videos: raise ValueError('Playlist data must include a name and at least one video.')
        self.tags = sorted(list(set([tag.strip().lower() for tag in self.tags if tag.strip()])))
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
    upvotes_count: int = 0
    downvotes_count: int = 0
    user_vote: int = 0
    class Config: json_encoders = {ObjectId: str}; populate_by_name = True

class FeedResponse(BaseModel):
    posts: list[PostOut]
    has_more: bool

class VoteRequest(BaseModel):
    direction: int = Field(..., ge=-1, le=1)

# ==============================================================================
# 3. HELPER & DEPENDENCY FUNCTIONS
# ==============================================================================
def create_jwt_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "token_type": token_type})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(username: str) -> str:
    return create_jwt_token(data={"sub": username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), token_type="access")

def create_refresh_token(username: str) -> str:
    return create_jwt_token(data={"sub": username}, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), token_type="refresh")

async def get_current_user_from_token(token: str) -> UserInDB | None:
    if not token: return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access": return None
        username: str | None = payload.get("sub")
        if not username: return None
        user = users_collection.find_one({"username": username})
        return UserInDB(**user) if user else None
    except (PyJWTError, ValueError): return None

async def get_optional_current_user(request: Request) -> UserInDB | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header: return None
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer": return None
        return await get_current_user_from_token(token)
    except ValueError: return None
    
async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    user = await get_current_user_from_token(token)
    if user is None: raise credentials_exception
    return user

async def get_circle_or_404(circle_id: str) -> dict:
    if not ObjectId.is_valid(circle_id): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Circle ID")
    circle = circles_collection.find_one({"_id": ObjectId(circle_id)})
    if not circle: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Circle not found")
    return circle

async def check_circle_membership(current_user: UserInDB = Depends(get_current_user), circle: dict = Depends(get_circle_or_404)) -> dict:
    if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
        if not circle["is_public"] or ("password_hash" in circle and circle["password_hash"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this circle.")
    return circle

def _get_posts_aggregation_pipeline(match_stage: dict, sort_stage: dict, skip: int, limit: int, current_user: UserInDB | None) -> list[dict]:
    pipeline = [match_stage]
    add_fields_stage = {"$addFields": {"upvotes_count": {"$size": {"$ifNull": ["$upvotes", []]}}, "downvotes_count": {"$size": {"$ifNull": ["$downvotes", []]}}}}
    pipeline.append(add_fields_stage)
    pipeline.append({"$addFields": {"score": {"$subtract": ["$upvotes_count", "$downvotes_count"]}}})
    if current_user:
        pipeline.append({"$addFields": {"user_vote": {"$cond": {"if": {"$in": [current_user.id, {"$ifNull": ["$upvotes", []]}]}, "then": 1, "else": {"$cond": {"if": {"$in": [current_user.id, {"$ifNull": ["$downvotes", []]}]}, "then": -1, "else": 0}}}}}})
    pipeline.extend([sort_stage, {"$skip": skip}, {"$limit": limit}])
    return pipeline
    
# ==============================================================================
# 4. WEBSOCKET & CHAT MANAGER
# ==============================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, circle_id: str, user: UserInDB):
        await websocket.accept()
        if circle_id not in self.active_connections:
            self.active_connections[circle_id] = {}
        
        join_msg = {"type": "user-joined", "user_id": str(user.id), "username": user.username}
        await self.broadcast(json.dumps(join_msg), circle_id, websocket)

        user_list = [{"user_id": uid, "username": ws.scope["user"].username} for uid, ws in self.active_connections[circle_id].items()]
        await websocket.send_json({"type": "existing-users", "users": user_list})

        history_cursor = chat_messages_collection.find({"circle_id": ObjectId(circle_id)}).sort("timestamp", DESCENDING).limit(50)
        
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

    async def broadcast(self, message: str, circle_id: str, exclude: WebSocket | None = None):
        if circle_id in self.active_connections:
            for connection in self.active_connections[circle_id].values():
                if connection != exclude:
                    await connection.send_text(message)
    
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
    is_member = any(m['user_id'] == user.id for m in circle.get('members', []))
    if not is_member:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = str(user.id)
    await manager.connect(websocket, circle_id, user)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            # ** THE FIX FOR VIDEO STATE **
            if msg_type in ["offer", "answer", "candidate"]:
                # Peer-to-peer messages for WebRTC signaling
                recipient_id = message.get("to")
                message["from"] = user_id
                await manager.send_personal_message(json.dumps(message), recipient_id, circle_id)
            elif msg_type == "media-state":
                # State changes (video/mic on/off) must be broadcast to everyone
                message["from"] = user_id
                await manager.broadcast(json.dumps(message), circle_id, exclude=websocket)
            elif msg_type == "chat":
                # Chat messages are saved and then broadcast to all (including sender)
                chat_message = ChatMessage(
                    circle_id=ObjectId(circle_id),
                    sender_id=user.id,
                    sender_username=user.username,
                    content=message.get("content", "")
                )
                chat_messages_collection.insert_one(chat_message.model_dump(by_alias=True))
                
                broadcast_msg = {
                    "type": "chat",
                    "_id": str(chat_message.id),
                    "sender_id": str(user.id),
                    "sender_username": user.username,
                    "content": chat_message.content,
                    "timestamp": chat_message.timestamp.isoformat()
                }
                await manager.broadcast(json.dumps(broadcast_msg), circle_id)
            else:
                 # Fallback for any other general messages
                message["from"] = user_id
                await manager.broadcast(json.dumps(message), circle_id, exclude=websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, circle_id, user_id)
        await manager.broadcast(json.dumps({"type": "user-left", "user_id": user_id}), circle_id)


# ==============================================================================
# 5. API ENDPOINTS
# ==============================================================================

# --- Authentication Endpoints ---
@app.post("/auth/register", response_model=UserPublicProfile, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register_user(user_data: UserRegister):
    if users_collection.find_one({"username": user_data.username}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    new_user_doc = {"username": user_data.username, "password_hash": pwd_context.hash(user_data.password), "following": [], "followers": []}
    result = users_collection.insert_one(new_user_doc)
    created_user = users_collection.find_one({"_id": result.inserted_id})
    return UserPublicProfile(**created_user, following_count=0, followers_count=0)

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login_for_access_token(form_data: UserAuth):
    user = users_collection.find_one({"username": form_data.username})
    if not user or not pwd_context.verify(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token = create_access_token(user["username"])
    refresh_token = create_refresh_token(user["username"])
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@app.post("/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
async def refresh_access_token(body: TokenRefreshRequest):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh": raise credentials_exception
        username: str | None = payload.get("sub")
        if username is None: raise credentials_exception
    except PyJWTError: raise credentials_exception
    user = users_collection.find_one({"username": username})
    if user is None: raise credentials_exception
    new_access_token = create_access_token(username)
    new_refresh_token = create_refresh_token(username)
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)

# --- User & Follow Request Endpoints ---
@app.get("/users/me", response_model=UserPrivateProfile, tags=["Users"])
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    pipeline = [
        {"$match": {"_id": current_user.id}},
        {"$lookup": {"from": "users", "localField": "following", "foreignField": "_id", "as": "following_details"}},
        {"$lookup": {
            "from": "follow_requests", "localField": "_id", "foreignField": "recipient_id", "as": "incoming_requests_docs",
            "pipeline": [
                {"$lookup": { "from": "users", "localField": "requester_id", "foreignField": "_id", "as": "requester_details"}},
                {"$unwind": "$requester_details"},
                {"$addFields": {"requester": { "_id": "$requester_details._id", "username": "$requester_details.username", "followers_count": {"$size": {"$ifNull": ["$requester_details.followers", []]}}, "following_count": {"$size": {"$ifNull": ["$requester_details.following", []]}}}}},
                {"$project": {"requester_details": 0, "recipient_id": 0, "requester_id": 0}}
            ]
        }},
        {"$lookup": {"from": "follow_requests", "localField": "_id", "foreignField": "requester_id", "as": "outgoing_requests_docs"}},
        {"$addFields": {
            "followers_count": {"$size": {"$ifNull": ["$followers", []]}}, "following_count": {"$size": {"$ifNull": ["$following", []]}},
            "following": { "$map": { "input": "$following_details", "as": "user", "in": { "_id": "$$user._id", "username": "$$user.username", "followers_count": {"$size": {"$ifNull": ["$$user.followers", []]}}, "following_count": {"$size": {"$ifNull": ["$$user.following", []]}}}}},
            "incoming_requests": "$incoming_requests_docs", "outgoing_requests": "$outgoing_requests_docs.recipient_id"
        }}
    ]
    result = list(users_collection.aggregate(pipeline))
    if not result: raise HTTPException(status_code=404, detail="User not found")
    return UserPrivateProfile(**result[0])

@app.get("/users/suggestions", response_model=list[UserPublicProfile], tags=["Users"])
async def get_user_suggestions(current_user: UserInDB = Depends(get_current_user), limit: int = Query(5, ge=1, le=20)):
    pipeline = [{"$match": {"members.user_id": current_user.id}}, {"$unwind": "$members"}, {"$group": {"_id": "$members.user_id"}}, {"$match": {"_id": {"$nin": [current_user.id] + current_user.following}}}, {"$limit": limit}, {"$lookup": { "from": "users", "localField": "_id", "foreignField": "_id", "as": "user_details" }}, {"$unwind": "$user_details"}, {"$replaceRoot": {"newRoot": "$user_details"}}, {"$addFields": {"followers_count": {"$size": "$followers"}, "following_count": {"$size": "$following"}}}, {"$project": { "password_hash": 0, "following": 0, "followers": 0 }}]
    suggestions_cursor = circles_collection.aggregate(pipeline)
    return [UserPublicProfile(**user) for user in suggestions_cursor]

@app.get("/users/discover", response_model=list[UserPublicProfile], tags=["Users"])
async def discover_users(q: str = Query(..., min_length=1), current_user: UserInDB = Depends(get_current_user), limit: int = Query(10, ge=1, le=25)):
    safe_query = re.escape(q)
    pipeline = [{"$match": {"username": {"$regex": safe_query, "$options": "i"}, "_id": {"$ne": current_user.id}}}, {"$limit": limit}, {"$addFields": {"followers_count": {"$size": "$followers"},"following_count": {"$size": "$following"}}}, {"$project": { "password_hash": 0, "following": 0, "followers": 0 }}]
    results = list(users_collection.aggregate(pipeline))
    return [UserPublicProfile(**user) for user in results]

@app.post("/users/{username_to_request}/request-follow", status_code=status.HTTP_201_CREATED, tags=["Users"])
async def request_to_follow_user(username_to_request: str, current_user: UserInDB = Depends(get_current_user)):
    if current_user.username.lower() == username_to_request.lower(): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot send a follow request to yourself.")
    recipient = users_collection.find_one({"username": {"$regex": f"^{re.escape(username_to_request)}$", "$options": "i"}})
    if not recipient: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if recipient["_id"] in current_user.following: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already following this user.")
    if follow_requests_collection.find_one({"requester_id": current_user.id, "recipient_id": recipient["_id"]}): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already sent a follow request to this user.")
    follow_requests_collection.insert_one({"requester_id": current_user.id, "recipient_id": recipient["_id"], "created_at": datetime.now(timezone.utc)})
    return {"detail": "Follow request sent successfully."}

@app.delete("/users/{recipient_username}/cancel-request", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def cancel_follow_request(recipient_username: str, current_user: UserInDB = Depends(get_current_user)):
    recipient = users_collection.find_one({"username": {"$regex": f"^{re.escape(recipient_username)}$", "$options": "i"}})
    if not recipient: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    follow_requests_collection.delete_one({"requester_id": current_user.id, "recipient_id": recipient["_id"]})

@app.post("/users/me/follow-requests/{request_id}/respond", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def respond_to_follow_request(request_id: str, body: RespondToRequest, current_user: UserInDB = Depends(get_current_user)):
    if not ObjectId.is_valid(request_id): raise HTTPException(status_code=400, detail="Invalid request ID.")
    request_obj_id = ObjectId(request_id)
    request_doc = follow_requests_collection.find_one({"_id": request_obj_id})
    if not request_doc or request_doc["recipient_id"] != current_user.id: raise HTTPException(status_code=404, detail="Follow request not found or you are not the recipient.")
    if body.action == "accept":
        users_collection.update_one({"_id": current_user.id}, {"$addToSet": {"followers": request_doc["requester_id"]}})
        users_collection.update_one({"_id": request_doc["requester_id"]}, {"$addToSet": {"following": current_user.id}})
    follow_requests_collection.delete_one({"_id": request_obj_id})

@app.delete("/users/{username_to_unfollow}/follow", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def unfollow_user(username_to_unfollow: str, current_user: UserInDB = Depends(get_current_user)):
    target_user = users_collection.find_one({"username": {"$regex": f"^{re.escape(username_to_unfollow)}$", "$options": "i"}})
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to unfollow not found")
    users_collection.update_one({"_id": current_user.id}, {"$pull": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$pull": {"followers": current_user.id}})

@app.post("/users/me/generate-follow-token", response_model=FollowTokenCreateResponse, tags=["Users"])
async def generate_follow_token(current_user: UserInDB = Depends(get_current_user)):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=FOLLOW_TOKEN_EXPIRE_MINUTES)
    follow_tokens_collection.insert_one({"token": token, "user_id_to_follow": current_user.id, "created_at": datetime.now(timezone.utc), "expires_at": expires_at})
    return FollowTokenCreateResponse(token=token, expires_at=expires_at)

@app.post("/users/follow-by-token", response_model=FollowByTokenResponse, tags=["Users"])
async def follow_by_token(body: FollowByTokenRequest, current_user: UserInDB = Depends(get_current_user)):
    token_doc = follow_tokens_collection.find_one_and_delete({"token": body.token, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not token_doc: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Follow link is invalid or has expired.")
    target_user_id = token_doc["user_id_to_follow"]
    if current_user.id == target_user_id: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot use a follow link for yourself.")
    target_user = users_collection.find_one({"_id": target_user_id})
    if not target_user: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The user associated with this link could not be found.")
    users_collection.update_one({"_id": current_user.id}, {"$addToSet": {"following": target_user_id}})
    users_collection.update_one({"_id": target_user_id}, {"$addToSet": {"followers": current_user.id}})
    return FollowByTokenResponse(followed_username=target_user["username"])

# --- Circle & Post Endpoints ---
@app.get("/circles/mine", response_model=list[CircleOut], tags=["Circles"])
async def list_my_circles(current_user: UserInDB = Depends(get_current_user)):
    circles_cursor = circles_collection.find({"members.user_id": current_user.id}).sort("name", ASCENDING)
    return [CircleOut(**c, member_count=len(c.get("members", [])), is_password_protected="password_hash" in c and c.get("password_hash") is not None) for c in circles_cursor]

@app.post("/circles", response_model=CircleOut, status_code=status.HTTP_201_CREATED, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
    first_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.admin)
    new_circle_doc = {"name": circle_data.name, "description": circle_data.description, "is_public": circle_data.is_public, "owner_id": current_user.id, "members": [first_member.model_dump()], "created_at": datetime.now(timezone.utc)}
    if circle_data.password: new_circle_doc["password_hash"] = pwd_context.hash(circle_data.password)
    result = circles_collection.insert_one(new_circle_doc)
    created_circle = circles_collection.find_one({"_id": result.inserted_id})
    is_protected = "password_hash" in created_circle and created_circle.get("password_hash") is not None
    return CircleOut(**created_circle, member_count=1, is_password_protected=is_protected)

@app.get("/circles/{circle_id}/status", response_model=CircleStatusOut, tags=["Circles"])
async def get_circle_public_status(circle: dict = Depends(get_circle_or_404)):
    is_protected = "password_hash" in circle and circle.get("password_hash") is not None
    return CircleStatusOut(name=circle["name"], is_password_protected=is_protected)

@app.post("/circles/{circle_id}/join", status_code=status.HTTP_204_NO_CONTENT, tags=["Circles"])
async def join_password_protected_circle(join_data: CircleJoin, circle: dict = Depends(get_circle_or_404), current_user: UserInDB = Depends(get_current_user)):
    if not circle.get("password_hash"): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This circle is not password protected.")
    if any(m['user_id'] == current_user.id for m in circle.get("members", [])): return
    if not pwd_context.verify(join_data.password, circle["password_hash"]): raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password")
    new_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.member)
    circles_collection.update_one({"_id": circle["_id"]}, {"$addToSet": {"members": new_member.model_dump()}})

@app.post("/circles/{circle_id}/invite-token", response_model=InviteTokenCreateResponse, tags=["Circles"])
async def create_invite_token(circle: dict = Depends(check_circle_membership)):
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_TOKEN_EXPIRE_HOURS)
    invite_tokens_collection.insert_one({"token": token, "circle_id": circle["_id"], "expires_at": expires_at})
    return InviteTokenCreateResponse(token=token, expires_at=expires_at)
    
@app.post("/circles/join-by-token", response_model=JoinByTokenResponse, tags=["Circles"])
async def join_circle_by_token(body: JoinByTokenRequest, current_user: UserInDB = Depends(get_current_user)):
    token_doc = invite_tokens_collection.find_one({"token": body.token, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not token_doc: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite link is invalid or has expired.")
    circle = circles_collection.find_one({"_id": token_doc["circle_id"]})
    if not circle: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The circle associated with this invite no longer exists.")
    if any(m['user_id'] == current_user.id for m in circle.get("members", [])):
        return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])
    new_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.member)
    circles_collection.update_one({"_id": circle["_id"]}, {"$addToSet": {"members": new_member.model_dump()}})
    return JoinByTokenResponse(circle_id=str(circle["_id"]), circle_name=circle["name"])

@app.get("/circles/{circle_id}", response_model=CircleOut, tags=["Circles"])
async def get_circle_details(circle: dict = Depends(check_circle_membership)):
    is_protected = "password_hash" in circle and circle.get("password_hash") is not None
    return CircleOut(**circle, member_count=len(circle.get("members", [])), is_password_protected=is_protected)

@app.get("/circles/{circle_id}/feed", response_model=FeedResponse, tags=["Circles"])
async def get_circle_feed(circle_id: str, skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50), sort_by: SortByEnum = Query(SortByEnum.newest), tags: str | None = Query(None), current_user: UserInDB | None = Depends(get_optional_current_user)):
    circle = await get_circle_or_404(circle_id)
    is_member = current_user and any(m['user_id'] == current_user.id for m in circle.get('members', []))
    can_view = circle["is_public"] or is_member
    if not can_view:
        if "password_hash" in circle and circle["password_hash"]:
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This circle is password protected. Please join to view.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be a member to view this circle's feed.")

    match_query = {"circle_id": circle["_id"]}
    if tags:
        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_list: match_query["content.tags"] = {"$all": tag_list}
    match_stage = {"$match": match_query}
    count_pipeline = [match_stage, {"$count": "total"}]
    total_posts = next(posts_collection.aggregate(count_pipeline), {}).get("total", 0)
    sort_stage = {"$sort": {"score": DESCENDING, "created_at": DESCENDING}} if sort_by == SortByEnum.top else {"$sort": {"created_at": DESCENDING}}
    posts_pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
    posts_cursor = posts_collection.aggregate(posts_pipeline)
    posts_list = [PostOut(**p, circle_name=circle["name"]) for p in posts_cursor]
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)

@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, tags=["Posts"])
async def create_post_in_circle(post_data: PostCreate, circle: dict = Depends(check_circle_membership), current_user: UserInDB = Depends(get_current_user)):
    new_post = {"circle_id": circle["_id"], "author_id": current_user.id, "author_username": current_user.username, "content": post_data.model_dump(exclude_unset=True), "created_at": datetime.now(timezone.utc), "upvotes": [], "downvotes": [], "score": 0}
    result = posts_collection.insert_one(new_post)
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    return PostOut(**created_post, circle_name=circle["name"])

@app.post("/posts/{post_id}/vote", status_code=status.HTTP_200_OK, tags=["Posts"])
async def vote_on_post(post_id: str, vote_data: VoteRequest, current_user: UserInDB = Depends(get_current_user)):
    if not ObjectId.is_valid(post_id): raise HTTPException(status_code=400, detail="Invalid Post ID")
    post_object_id = ObjectId(post_id)
    posts_collection.update_one({"_id": post_object_id}, {"$pull": {"upvotes": current_user.id, "downvotes": current_user.id}})
    if direction := vote_data.direction:
        field_to_update = "upvotes" if direction == 1 else "downvotes"
        posts_collection.update_one({"_id": post_object_id}, {"$addToSet": {field_to_update: current_user.id}})
    pipeline = [{"$match": {"_id": post_object_id}}, {"$project": {"score": {"$subtract": [{"$size": {"$ifNull": ["$upvotes", []]}}, {"$size": {"$ifNull": ["$downvotes", []]}}]}}}]
    result = list(posts_collection.aggregate(pipeline))
    if not result: raise HTTPException(status_code=404, detail="Post not found after voting")
    new_score = result[0]['score']
    posts_collection.update_one({"_id": post_object_id}, {"$set": {"score": new_score}})
    return {"status": "success", "new_score": new_score}

@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Posts"])
async def delete_post(circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user), circle: dict = Depends(get_circle_or_404)):
    if not ObjectId.is_valid(post_id): raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Post ID")
    post = posts_collection.find_one({"_id": ObjectId(post_id), "circle_id": ObjectId(circle_id)})
    if not post: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found in this circle")
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    user_is_mod_or_admin = member_info and RoleEnum(member_info['role']) in [RoleEnum.moderator, RoleEnum.admin]
    if not (post['author_id'] == current_user.id or user_is_mod_or_admin): raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete this post")
    posts_collection.delete_one({"_id": ObjectId(post_id)})

@app.get("/feed", response_model=FeedResponse, tags=["Feed"])
async def get_my_feed(current_user: UserInDB = Depends(get_current_user), skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50), circle_id: str | None = Query(None), sort_by: SortByEnum = Query(SortByEnum.newest), tags: str | None = Query(None)):
    user_circles_cursor = circles_collection.find({"members.user_id": current_user.id}, {"_id": 1, "name": 1})
    user_circles = {c["_id"]: c["name"] for c in user_circles_cursor}
    if not user_circles: return FeedResponse(posts=[], has_more=False)
    match_query = {}
    if circle_id:
        if not ObjectId.is_valid(circle_id) or ObjectId(circle_id) not in user_circles: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot filter by a circle you are not a member of.")
        match_query["circle_id"] = ObjectId(circle_id)
    else:
        match_query["circle_id"] = {"$in": list(user_circles.keys())}
    if tags:
        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_list: match_query["content.tags"] = {"$all": tag_list}
    match_stage = {"$match": match_query}
    count_pipeline = [match_stage, {"$count": "total"}]
    total_posts = next(posts_collection.aggregate(count_pipeline), {}).get("total", 0)
    sort_stage = {"$sort": {"score": DESCENDING, "created_at": DESCENDING}} if sort_by == SortByEnum.top else {"$sort": {"created_at": DESCENDING}}
    posts_pipeline = _get_posts_aggregation_pipeline(match_stage, sort_stage, skip, limit, current_user)
    posts_cursor = posts_collection.aggregate(posts_pipeline)
    posts_list = [PostOut(**p, circle_name=user_circles.get(p["circle_id"], "Unknown")) for p in posts_cursor]
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)

# ==============================================================================
# 6. STATIC FILE SERVING
# ==============================================================================
if not os.path.exists("static"): os.makedirs("static"); print("Created 'static' directory.")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_frontend(full_path: str):
    static_file_path = "static/index.html"
    if ".." in full_path: raise HTTPException(status_code=404, detail="Not Found")
    requested_path = os.path.join("static", full_path)
    if full_path and os.path.isfile(requested_path): return FileResponse(requested_path)
    if not os.path.exists(static_file_path): raise HTTPException(status_code=404, detail="Frontend entry point not found.")
    return FileResponse(static_file_path)

# ==============================================================================
# 7. SERVER EXECUTION
# ==============================================================================
if __name__ == "__main__":
    print("Starting server...")
    print("Access the API docs at http://127.0.0.1:8000/docs")
    print("Access the User Interface at http://127.0.0.1:8000/")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
"""
uvicorn main:app --reload
"""
