# ==============================================================================
# 0. IMPORTS
# ==============================================================================
# Standard library imports for OS interaction, time/date handling, and type hinting.
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from contextlib import asynccontextmanager
from enum import Enum

# Third-party library imports.
import uvicorn  # ASGI server for running the application.
import jwt      # For encoding and decoding JSON Web Tokens (JWTs).
from jwt.exceptions import PyJWTError

from fastapi import FastAPI, HTTPException, Body, Depends, status, Query
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
# WARNING: In a production environment, this key should be loaded from a secure
# environment variable and should be a long, complex, randomly generated string.
SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key-that-you-should-change")
ALGORITHM = "HS256"  # The algorithm used to sign the JWTs.
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Lifetime of a short-lived access token.
REFRESH_TOKEN_EXPIRE_DAYS = 7     # Lifetime of a long-lived refresh token.

# --- Database Configuration ---
# The connection string for the MongoDB database.
# It's best practice to load this from an environment variable.
MONGO_DETAILS = os.getenv("MONGO_URI", "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true")

# --- Global Objects & Instances ---
# Establish a connection to the MongoDB server.
client = MongoClient(MONGO_DETAILS)
# Select the database to use.
db = client.circles_app

# Get a handle to the specific collections (like tables in SQL).
users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")

# Create a CryptContext instance for password hashing. We specify 'bcrypt' as the
# scheme, which is a strong, widely-used hashing algorithm.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This creates an OAuth2-compatible security scheme. FastAPI uses this to generate
# the "Authorize" button in the interactive API docs (e.g., /docs).
# The `tokenUrl` points to the endpoint where the client can exchange credentials for a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# --- Application Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    An async context manager to handle application startup and shutdown events.
    This is the modern way to manage resources in FastAPI (replaces on_event).
    """
    print("✅ Connecting to MongoDB...")
    # --- Startup Logic ---
    # Create indexes on collections to improve query performance and enforce uniqueness.
    # `unique=True` on username ensures no two users can have the same username.
    users_collection.create_index([("username", ASCENDING)], unique=True)
    circles_collection.create_index([("name", ASCENDING)])
    posts_collection.create_index([("circle_id", ASCENDING)])
    posts_collection.create_index([("created_at", DESCENDING)])
    print("🚀 Database connection established and indexes ensured.")
    
    yield  # The application runs while the 'yield' is active.
    
    # --- Shutdown Logic ---
    # This code runs after the application is shutting down.
    client.close()
    print("🔌 Database connection closed.")

# Initialize the main FastAPI application instance.
app = FastAPI(
    title="Circles Social API",
    description="A complete API for a social application with user authentication, circles, roles, and posts.",
    version="1.2.0",
    lifespan=lifespan,  # Register the lifespan manager.
)

# ==============================================================================
# 2. Pydantic MODELS (Data Schemas)
# ==============================================================================
# Pydantic models define the data shapes for API requests and responses.
# They provide data validation, serialization (e.g., Python object -> JSON),
# and are used by FastAPI to automatically generate API documentation.

class PyObjectId(ObjectId):
    """
    A custom Pydantic field type for MongoDB's ObjectId.
    
    This class allows us to use MongoDB's `ObjectId` in our Pydantic models
    and have it automatically validated and serialized.
    """
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class RoleEnum(str, Enum):
    """Enumeration for user roles within a circle."""
    member = "member"
    moderator = "moderator"
    admin = "admin"

# --- User Schemas ---

class UserRegister(BaseModel):
    """Schema for data required during user registration."""
    username: str = Field(..., min_length=3, max_length=50, description="The user's unique username.")
    password: str = Field(..., min_length=8, description="The user's password (will be hashed).")

class UserAuth(BaseModel):
    """Schema for user login credentials."""
    username: str
    password: str

class UserInDB(BaseModel):
    """Schema representing a user object as it is stored in the database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    username: str
    password_hash: str
    following: list[PyObjectId] = []
    followers: list[PyObjectId] = []
    
    class Config:
        json_encoders = {ObjectId: str} # Serialize ObjectId to string in JSON responses.
        populate_by_name = True # Allow using `_id` from DB to populate the `id` field.

class UserPublicProfile(BaseModel):
    """Schema for a user's public-facing profile information."""
    id: PyObjectId = Field(alias="_id")
    username: str
    following_count: int
    followers_count: int

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

class UserPrivateProfile(UserPublicProfile):
    """
    Schema for the logged-in user's own profile, which includes private details
    like the list of people they follow. Inherits from UserPublicProfile.
    """
    following: list[UserPublicProfile] = []

# --- Authentication Schemas ---

class TokenResponse(BaseModel):
    """Schema for the response when a user successfully logs in."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

# --- Circle Schemas ---

class CircleMember(BaseModel):
    """Schema representing a member within a circle's member list."""
    user_id: PyObjectId
    username: str
    role: RoleEnum = RoleEnum.member
    
    class Config:
        json_encoders = {ObjectId: str}
        
class CircleCreate(BaseModel):
    """Schema for the data needed to create a new circle."""
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_public: bool = True

class CircleOut(BaseModel):
    """Schema for representing a circle in API responses."""
    name: str
    description: str | None
    is_public: bool
    id: PyObjectId = Field(alias="_id")
    owner_id: PyObjectId
    member_count: int
    
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

# --- Post Schemas ---

class PostTypeEnum(str, Enum):
    text_update = "text_update"
    wishlist_item = "wishlist_item"
    youtube_video = "youtube_video"
    
class PostCreate(BaseModel):
    """Schema for creating a new post within a circle."""
    post_type: PostTypeEnum
    content: dict[str, Any] = Field(..., example={"text": "Hello world!"}, description="A flexible dictionary to store the post's content, allowing for different post structures.")

class PostOut(BaseModel):
    """Schema for representing a post in API responses."""
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
# These functions provide reusable logic. Dependency functions are special helpers
# that FastAPI can inject into endpoint operations to handle common tasks like
# authentication, database lookups, and permission checks.

# --- JWT Helper Functions ---

def create_jwt_token(data: dict, expires_delta: timedelta) -> str:
    """
    Creates a JWT with a specified payload and expiration time.

    Args:
        data: The dictionary payload to include in the token.
        expires_delta: A timedelta object representing the token's lifespan.

    Returns:
        A signed JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(username: str) -> str:
    """Convenience function to create a short-lived access token."""
    return create_jwt_token(data={"sub": username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(username: str) -> str:
    """Convenience function to create a long-lived refresh token."""
    return create_jwt_token(data={"sub": username}, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

# --- Dependency Functions ---

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """
    A dependency that decodes a JWT from the request's Authorization header,
    validates it, and fetches the corresponding user from the database.
    
    This function is used in any endpoint that requires an authenticated user.
    If the token is invalid or the user doesn't exist, it raises an HTTP 401 error.

    Args:
        token: The bearer token extracted from the request header by FastAPI.

    Returns:
        The authenticated user's data as a UserInDB object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
        
    user = users_collection.find_one({"username": username})
    if user is None:
        raise credentials_exception
        
    return UserInDB(**user)

async def get_circle_or_404(circle_id: str) -> dict:
    """
    A dependency that fetches a circle from the database by its ID.
    Raises a 404 Not Found error if the circle does not exist or if the ID is invalid.

    Args:
        circle_id: The string representation of the circle's ObjectId.

    Returns:
        A dictionary containing the circle's data.
    """
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
    """
    A dependency that verifies if the current user is allowed to access a circle.
    
    It first uses `get_circle_or_404` to fetch the circle. Then, it checks:
    1. If the circle is public, access is granted.
    2. If the circle is private, it checks if the current user is in the member list.
    
    If access is denied, it raises an HTTP 403 Forbidden error.

    Returns:
        The circle dictionary if access is permitted.
    """
    if circle["is_public"]:
        return circle
        
    if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this private circle")
        
    return circle

# ==============================================================================
# 4. API ENDPOINTS
# ==============================================================================
# This is the main part of the API, defining all the available routes (endpoints).
# Each function corresponds to an HTTP method and path.

# --- Authentication Endpoints ---

@app.post("/auth/register", response_model=UserPublicProfile, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register_user(user_data: UserRegister):
    """
    Registers a new user in the system.
    
    - Hashes the provided password for secure storage.
    - Checks if the username is already taken.
    """
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
    """
    Authenticates a user and returns access and refresh tokens.
    
    - Verifies the username and password.
    - If successful, generates and returns JWTs.
    """
    user = users_collection.find_one({"username": form_data.username})
    if not user or not pwd_context.verify(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
        
    access_token = create_access_token(user["username"])
    refresh_token = create_refresh_token(user["username"])
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

# --- User Endpoints ---

@app.get("/users/me", response_model=UserPrivateProfile, tags=["Users"])
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    """
    Fetches the profile details for the currently authenticated user.
    This includes private information like the list of users they follow.
    
    **Requires Authentication.**
    """
    following_users_cursor = users_collection.find({"_id": {"$in": current_user.following}})
    following_users = [
        UserPublicProfile(**u, following_count=len(u.get("following", [])), followers_count=len(u.get("followers", []))) 
        for u in following_users_cursor
    ]
    
    user_data = current_user.model_dump(by_alias=True)
    user_data.pop("following", None)

    return UserPrivateProfile(
        **user_data,
        following_count=len(current_user.following),
        followers_count=len(current_user.followers),
        following=following_users
    )

@app.get("/users", response_model=list[UserPublicProfile], tags=["Users"])
async def list_all_users():
    """Retrieves a list of all public user profiles."""
    users_cursor = users_collection.find({})
    return [
        UserPublicProfile(**u, following_count=len(u.get("following", [])), followers_count=len(u.get("followers", [])))
        for u in users_cursor
    ]

@app.post("/users/{username_to_follow}/follow", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def follow_user(username_to_follow: str, current_user: UserInDB = Depends(get_current_user)):
    """
    Allows the current user to follow another user.
    
    - This is an idempotent operation; following a user you already follow has no effect.
    
    **Requires Authentication.**
    """
    if current_user.username == username_to_follow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself")
        
    target_user = users_collection.find_one({"username": username_to_follow})
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found")
    
    users_collection.update_one({"_id": current_user.id}, {"$addToSet": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$addToSet": {"followers": current_user.id}})

@app.delete("/users/{username_to_unfollow}/follow", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def unfollow_user(username_to_unfollow: str, current_user: UserInDB = Depends(get_current_user)):
    """
    Allows the current user to unfollow another user.
    
    **Requires Authentication.**
    """
    target_user = users_collection.find_one({"username": username_to_unfollow})
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to unfollow not found")

    users_collection.update_one({"_id": current_user.id}, {"$pull": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$pull": {"followers": current_user.id}})

# --- Circle Endpoints ---

@app.get("/circles/mine", response_model=list[CircleOut], tags=["Circles"])
async def list_my_circles(current_user: UserInDB = Depends(get_current_user)):
    """
    Retrieves a list of all circles the current user is a member of.
    """
    circles_cursor = circles_collection.find({"members.user_id": current_user.id}).sort("name", ASCENDING)
    return [CircleOut(**c, member_count=len(c.get("members", []))) for c in circles_cursor]

@app.post("/circles", response_model=CircleOut, status_code=status.HTTP_201_CREATED, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
    """
    Creates a new circle.
    
    - The user who creates the circle automatically becomes its first member and admin.
    
    **Requires Authentication.**
    """
    first_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.admin)
    
    new_circle_doc = {
        "name": circle_data.name, 
        "description": circle_data.description, 
        "is_public": circle_data.is_public,
        "owner_id": current_user.id, 
        "members": [first_member.model_dump()], 
        "created_at": datetime.now(timezone.utc)
    }
    
    result = circles_collection.insert_one(new_circle_doc)
    created_circle = circles_collection.find_one({"_id": result.inserted_id})
    
    return CircleOut(**created_circle, member_count=1)

@app.get("/circles/{circle_id}", response_model=CircleOut, tags=["Circles"])
async def get_circle_details(circle: dict = Depends(check_circle_membership)):
    """
    Retrieves the details for a specific circle.
    
    - Access is controlled by the `check_circle_membership` dependency.
    
    **Requires Authentication for private circles.**
    """
    return CircleOut(**circle, member_count=len(circle.get("members", [])))

# --- Post & Feed Endpoints ---

@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, tags=["Posts"])
async def create_post_in_circle(post_data: PostCreate, circle: dict = Depends(check_circle_membership), current_user: UserInDB = Depends(get_current_user)):
    """
    Creates a new post within a specific circle.
    
    - The user must be a member of the circle to post.
    
    **Requires Authentication.**
    """
    new_post = {
        "circle_id": circle["_id"], 
        "author_id": current_user.id, 
        "author_username": current_user.username, 
        "post_type": post_data.post_type.value, 
        "content": post_data.content, 
        "created_at": datetime.now(timezone.utc)
    }
    result = posts_collection.insert_one(new_post)
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    return PostOut(**created_post, circle_name=circle["name"])

@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Posts"])
async def delete_post(circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user), circle: dict = Depends(get_circle_or_404)):
    """
    Deletes a post from a circle.
    
    - A user can delete their own post.
    - A moderator or admin of the circle can delete any post in the circle.
    
    **Requires Authentication.**
    """
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
    """
    Retrieves a personalized feed for the current user.
    
    - The feed consists of posts from all circles the user is a member of.
    - Supports pagination using `skip` and `limit`.
    - Can be filtered to show posts from only one circle via `circle_id`.
    
    **Requires Authentication.**
    """
    # FIX: Removed the restrictive projection `{"_id": 1, "name": 1}` to ensure
    # the validation check works reliably with the full circle documents.
    user_circles_cursor = circles_collection.find(
        {"members.user_id": current_user.id}
    )
    user_circles = {c["_id"]: c["name"] for c in user_circles_cursor}

    if not user_circles:
        return FeedResponse(posts=[], has_more=False)
    
    if circle_id:
        # If a circle_id is provided, validate it.
        if not ObjectId.is_valid(circle_id) or ObjectId(circle_id) not in user_circles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Cannot filter by a circle you are not a member of."
            )
        # If valid, set the match stage to filter by that specific ID.
        match_stage = {"$match": {"circle_id": ObjectId(circle_id)}}
    else:
        # If no circle_id was provided, fetch from all of the user's circles.
        match_stage = {"$match": {"circle_id": {"$in": list(user_circles.keys())}}}
        
    count_pipeline = [
        match_stage, 
        {"$count": "total"}
    ]
    total_posts_cursor = posts_collection.aggregate(count_pipeline)
    total_posts = next(total_posts_cursor, {}).get("total", 0)

    posts_pipeline = [
        match_stage,
        {"$sort": {"created_at": DESCENDING}},
        {"$skip": skip},
        {"$limit": limit},
    ]
    posts_cursor = posts_collection.aggregate(posts_pipeline)

    posts_list = [
        PostOut(**p, circle_name=user_circles.get(p["circle_id"], "Unknown")) for p in posts_cursor
    ]
    
    return FeedResponse(
        posts=posts_list, 
        has_more=(skip + len(posts_list)) < total_posts
    )

# ==============================================================================
# 5. STATIC FILE SERVING
# ==============================================================================
# This section configures FastAPI to serve a frontend application (e.g., React, Vue).
# It uses a "catch-all" route to handle requests that don't match any API endpoints.

@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_frontend(full_path: str):
    """
    Serves the Single-Page Application (SPA) frontend.
    
    This catch-all route is crucial for SPAs. It ensures that any request
    not matching an API route (e.g., /profile, /settings) is handled by
    the frontend. It always serves the `index.html` file, allowing the
    frontend's router (like React Router) to manage the URL.
    """
    static_file_path = "static/index.html"
    if not os.path.exists(static_file_path):
        raise HTTPException(status_code=404, detail="Frontend entry point not found. Make sure 'static/index.html' exists.")
    return FileResponse(static_file_path)

# ==============================================================================
# 6. SERVER EXECUTION
# ==============================================================================

# This block allows the script to be run directly using `python main.py`.
# `uvicorn.run()` starts the ASGI server.
if __name__ == "__main__":
    print("Starting server...")
    print("Access the API docs at http://127.0.0.1:8000/docs")
    print("Access the User Interface at http://127.0.0.1:8000/")
    uvicorn.run(
        "main:app",      # The import string: 'filename:fastapi_instance_name'
        host="0.0.0.0",  # Listen on all available network interfaces
        port=8000,       # The port to run on
        reload=True      # The server will automatically restart when code changes are detected
    )
"""
uvicorn main:app --reload
"""
