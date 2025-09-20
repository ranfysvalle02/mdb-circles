# ==============================================================================
# 0. IMPORTS
# ==============================================================================
# Standard library imports for OS interaction, time/date handling, and type hinting.
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from contextlib import asynccontextmanager
from enum import Enum

# Third-party library imports.
import uvicorn  # ASGI server for running the application.
import jwt      # For encoding and decoding JSON Web Tokens (JWTs).
from jwt.exceptions import PyJWTError

from fastapi import FastAPI, HTTPException, Body, Depends, status, Query, Request ## --- CHANGE START --- ##: Added Request
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from passlib.context import CryptContext # For securely hashing passwords.
from pymongo import MongoClient, ASCENDING, DESCENDING # Driver for interacting with MongoDB.
from bson import ObjectId # For handling MongoDB's unique Object ID type.

# ==============================================================================
# 1. CONFIGURATION & INITIALIZATION
# ==============================================================================
# This section sets up all the core configurations, constants, and connections
# needed for the application to run.

# --- Security & JWT Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key-that-you-should-change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# --- Database Configuration ---
MONGO_DETAILS = os.getenv("MONGO_URI", "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true")

# --- Global Objects & Instances ---
client = MongoClient(MONGO_DETAILS)
db = client.circles_app
users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
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
    print("🚀 Database connection established and indexes ensured.")
    yield
    client.close()
    print("🔌 Database connection closed.")

# Initialize the main FastAPI application instance.
app = FastAPI(
    title="Circles Social API",
    description="A complete API for a social application with user authentication, circles, roles, and posts.",
    version="1.4.0", # Version Bump
    lifespan=lifespan,
)

# ==============================================================================
# 2. Pydantic MODELS (Data Schemas)
# ==============================================================================

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class RoleEnum(str, Enum):
    member = "member"
    moderator = "moderator"
    admin = "admin"

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
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

class UserPublicProfile(BaseModel):
    id: PyObjectId = Field(alias="_id")
    username: str
    following_count: int
    followers_count: int
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

class UserPrivateProfile(UserPublicProfile):
    following: list[UserPublicProfile] = []

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
    description: str | None = Field(None, max_length=500)
    is_public: bool = True

class CircleOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    description: str | None
    is_public: bool
    owner_id: PyObjectId
    member_count: int
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

class PostTypeEnum(str, Enum):
    text_update = "text_update"
    wishlist_item = "wishlist_item"
    youtube_video = "youtube_video"

class PostCreate(BaseModel):
    post_type: PostTypeEnum
    content: dict[str, Any] = Field(..., example={"text": "Hello world!"})

class PostOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    circle_id: PyObjectId
    circle_name: str
    author_id: PyObjectId
    author_username: str
    post_type: PostTypeEnum
    content: dict[str, Any]
    created_at: datetime
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

class FeedResponse(BaseModel):
    posts: list[PostOut]
    has_more: bool

# ==============================================================================
# 3. HELPER & DEPENDENCY FUNCTIONS
# ==============================================================================

def create_jwt_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "token_type": token_type
    })
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

## --- CHANGE START --- ##
# NEW DEPENDENCY: Gets the current user if a token is provided, but doesn't
# raise an error if the token is missing or invalid. Returns UserInDB or None.
async def get_optional_current_user(request: Request) -> UserInDB | None:
    """
    Checks for a valid access token in the request headers. If found, returns
    the corresponding user. If not found or invalid, returns None.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            return None
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access":
            return None # Must be an access token

        username: str | None = payload.get("sub")
        if not username:
            return None

        user = users_collection.find_one({"username": username})
        if not user:
            return None
            
        return UserInDB(**user)
    except (ValueError, PyJWTError):
        # Catches errors from split() or jwt.decode()
        return None
## --- CHANGE END --- ##

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        token_type: str | None = payload.get("token_type")
        if username is None or token_type != "access":
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
    user = users_collection.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return UserInDB(**user)

async def get_circle_or_404(circle_id: str) -> dict:
    if not ObjectId.is_valid(circle_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Circle ID")
    circle = circles_collection.find_one({"_id": ObjectId(circle_id)})
    if not circle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Circle not found")
    return circle

async def check_circle_membership(
    current_user: UserInDB = Depends(get_current_user),
    circle: dict = Depends(get_circle_or_404)
) -> dict:
    if circle["is_public"]:
        return circle
    if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this private circle")
    return circle

# ==============================================================================
# 4. API ENDPOINTS
# ==============================================================================

# --- Authentication Endpoints ---
@app.post("/auth/register", response_model=UserPublicProfile, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register_user(user_data: UserRegister):
    if users_collection.find_one({"username": user_data.username}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    new_user_doc = {
        "username": user_data.username,
        "password_hash": pwd_context.hash(user_data.password),
        "following": [],
        "followers": []
    }
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
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh":
            raise credentials_exception
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
    
    user = users_collection.find_one({"username": username})
    if user is None:
        raise credentials_exception
        
    new_access_token = create_access_token(username)
    new_refresh_token = create_refresh_token(username)
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)

# --- User Endpoints ---
@app.get("/users/me", response_model=UserPrivateProfile, tags=["Users"])
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    pipeline = [
        {"$match": {"_id": current_user.id}},
        {"$lookup": {
            "from": "users", "localField": "following", "foreignField": "_id", "as": "following_details"
        }},
        {"$addFields": {
            "followers_count": {"$size": "$followers"},
            "following_count": {"$size": "$following"},
            "following": {
                "$map": {
                    "input": "$following_details", "as": "user",
                    "in": { "_id": "$$user._id", "username": "$$user.username", "followers_count": {"$size": "$$user.followers"}, "following_count": {"$size": "$$user.following"}}
                }
            }
        }}
    ]
    result = list(users_collection.aggregate(pipeline))
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPrivateProfile(**result[0])

@app.get("/users/search", response_model=list[UserPublicProfile], tags=["Users"])
async def search_for_user(
    username: str = Query(..., min_length=1, description="The username to search for (case-insensitive)."),
    current_user: UserInDB = Depends(get_current_user)
):
    safe_username = re.escape(username)
    found_user = users_collection.find_one({
        "username": {"$regex": f"^{safe_username}$", "$options": "i"},
        "_id": {"$ne": current_user.id}
    })
    if not found_user:
        return []
    return [UserPublicProfile(**found_user, following_count=len(found_user.get("following", [])), followers_count=len(found_user.get("followers", [])))]

@app.post("/users/{username_to_follow}/follow", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def follow_user(username_to_follow: str, current_user: UserInDB = Depends(get_current_user)):
    if current_user.username.lower() == username_to_follow.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself")
    target_user = users_collection.find_one({"username": {"$regex": f"^{re.escape(username_to_follow)}$", "$options": "i"}})
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found")
    users_collection.update_one({"_id": current_user.id}, {"$addToSet": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$addToSet": {"followers": current_user.id}})

@app.delete("/users/{username_to_unfollow}/follow", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def unfollow_user(username_to_unfollow: str, current_user: UserInDB = Depends(get_current_user)):
    target_user = users_collection.find_one({"username": {"$regex": f"^{re.escape(username_to_unfollow)}$", "$options": "i"}})
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to unfollow not found")
    users_collection.update_one({"_id": current_user.id}, {"$pull": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$pull": {"followers": current_user.id}})

# --- Circle Endpoints ---
@app.get("/circles/mine", response_model=list[CircleOut], tags=["Circles"])
async def list_my_circles(current_user: UserInDB = Depends(get_current_user)):
    circles_cursor = circles_collection.find({"members.user_id": current_user.id}).sort("name", ASCENDING)
    return [CircleOut(**c, member_count=len(c.get("members", []))) for c in circles_cursor]

@app.post("/circles", response_model=CircleOut, status_code=status.HTTP_201_CREATED, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
    first_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.admin)
    new_circle_doc = {
        "name": circle_data.name, "description": circle_data.description,
        "is_public": circle_data.is_public, "owner_id": current_user.id,
        "members": [first_member.model_dump()], "created_at": datetime.now(timezone.utc)
    }
    result = circles_collection.insert_one(new_circle_doc)
    created_circle = circles_collection.find_one({"_id": result.inserted_id})
    return CircleOut(**created_circle, member_count=1)

@app.get("/circles/{circle_id}", response_model=CircleOut, tags=["Circles"])
async def get_circle_details(circle: dict = Depends(check_circle_membership)):
    return CircleOut(**circle, member_count=len(circle.get("members", [])))

## --- CHANGE START --- ##
# NEW ENDPOINT: Gets the feed for a specific circle, with permission checks.
@app.get("/circles/{circle_id}/feed", response_model=FeedResponse, tags=["Circles"])
async def get_circle_feed(
    circle_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    current_user: UserInDB | None = Depends(get_optional_current_user)
):
    """
    Retrieves the feed for a specific circle.
    - If the circle is public, anyone can view it.
    - If the circle is private, the user must be logged in and a member.
    """
    circle = await get_circle_or_404(circle_id)

    # Permission Check
    if not circle["is_public"]:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="You must be logged in to view this private circle's feed.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        is_member = any(m['user_id'] == current_user.id for m in circle.get('members', []))
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this private circle."
            )

    # Fetch posts for the circle
    match_stage = {"$match": {"circle_id": circle["_id"]}}
    
    count_pipeline = [match_stage, {"$count": "total"}]
    total_posts = next(posts_collection.aggregate(count_pipeline), {}).get("total", 0)

    posts_pipeline = [
        match_stage,
        {"$sort": {"created_at": DESCENDING}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    posts_cursor = posts_collection.aggregate(posts_pipeline)

    posts_list = [PostOut(**p, circle_name=circle["name"]) for p in posts_cursor]
    
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)
## --- CHANGE END --- ##

# --- Post & Feed Endpoints ---
@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, tags=["Posts"])
async def create_post_in_circle(post_data: PostCreate, circle: dict = Depends(check_circle_membership), current_user: UserInDB = Depends(get_current_user)):
    content, ptype = post_data.content, post_data.post_type
    if ptype == PostTypeEnum.text_update and not content.get("text"):
        raise HTTPException(status_code=422, detail="Text content cannot be empty for a text_update.")
    elif ptype == PostTypeEnum.wishlist_item and not (content.get("item_name") and content.get("url")):
        raise HTTPException(status_code=422, detail="Wishlist item must include 'item_name' and 'url'.")
    elif ptype == PostTypeEnum.youtube_video and not (content.get("title") and content.get("youtube_url")):
        raise HTTPException(status_code=422, detail="YouTube video post must include 'title' and 'youtube_url'.")
    new_post = {
        "circle_id": circle["_id"], "author_id": current_user.id,
        "author_username": current_user.username, "post_type": ptype.value,
        "content": content, "created_at": datetime.now(timezone.utc)
    }
    result = posts_collection.insert_one(new_post)
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    return PostOut(**created_post, circle_name=circle["name"])

@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Posts"])
async def delete_post(circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user), circle: dict = Depends(get_circle_or_404)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Post ID")
    post = posts_collection.find_one({"_id": ObjectId(post_id), "circle_id": ObjectId(circle_id)})
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found in this circle")
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    user_is_mod_or_admin = member_info and RoleEnum(member_info['role']) in [RoleEnum.moderator, RoleEnum.admin]
    user_is_author = post['author_id'] == current_user.id
    if not user_is_author and not user_is_mod_or_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete this post")
    posts_collection.delete_one({"_id": ObjectId(post_id)})
    return

@app.get("/feed", response_model=FeedResponse, tags=["Feed"])
async def get_my_feed(
    current_user: UserInDB = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    circle_id: str | None = Query(None, description="Filter feed by a specific circle ID.")
):
    user_circles_cursor = circles_collection.find({"members.user_id": current_user.id})
    user_circles = {c["_id"]: c["name"] for c in user_circles_cursor}

    if not user_circles:
        return FeedResponse(posts=[], has_more=False)
    
    if circle_id:
        if not ObjectId.is_valid(circle_id) or ObjectId(circle_id) not in user_circles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot filter by a circle you are not a member of.")
        match_stage = {"$match": {"circle_id": ObjectId(circle_id)}}
    else:
        match_stage = {"$match": {"circle_id": {"$in": list(user_circles.keys())}}}
        
    count_pipeline = [match_stage, {"$count": "total"}]
    total_posts = next(posts_collection.aggregate(count_pipeline), {}).get("total", 0)

    posts_pipeline = [match_stage, {"$sort": {"created_at": DESCENDING}}, {"$skip": skip}, {"$limit": limit}]
    posts_cursor = posts_collection.aggregate(posts_pipeline)

    posts_list = [PostOut(**p, circle_name=user_circles.get(p["circle_id"], "Unknown")) for p in posts_cursor]
    
    return FeedResponse(posts=posts_list, has_more=(skip + len(posts_list)) < total_posts)

# ==============================================================================
# 5. STATIC FILE SERVING
# ==============================================================================
if not os.path.exists("static"):
    os.makedirs("static")
    print("Created 'static' directory for frontend files.")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_frontend(full_path: str):
    static_file_path = "static/index.html"
    if not os.path.exists(static_file_path):
        return HTTPException(status_code=404, detail="Frontend entry point not found.")
    return FileResponse(static_file_path)

# ==============================================================================
# 6. SERVER EXECUTION
# ==============================================================================
if __name__ == "__main__":
    print("Starting server...")
    print("Access the API docs at http://127.0.0.1:8000/docs")
    print("Access the User Interface at http://127.0.0.1:8000/")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
"""
uvicorn main:app --reload
"""
