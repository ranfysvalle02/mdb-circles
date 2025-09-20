# ==============================================================================
# 0. IMPORTS
# ==============================================================================
# Standard library imports for OS interaction, time/date handling, and type hinting.
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from contextlib import asynccontextmanager
from enum import Enum

# Third-party library imports.
import uvicorn  # ASGI server for running the application.
import jwt      # For encoding and decoding JSON Web Tokens (JWTs).
from jwt.exceptions import PyJWTError

from fastapi import FastAPI, HTTPException, Body, Depends, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from passlib.context import CryptContext # For securely hashing passwords.
from pymongo import MongoClient, ASCENDING # Driver for interacting with MongoDB.
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
    version="1.0.0",
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
    following: List[PyObjectId] = []
    followers: List[PyObjectId] = []
    
    class Config:
        json_encoders = {ObjectId: str} # Serialize ObjectId to string in JSON responses.
        populate_by_name = True # Allow using `_id` from DB to populate the `id` field.

class UserPublicProfile(BaseModel):
    """Schema for a user's public-facing profile information."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
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
    following: List[UserPublicProfile] = []

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

class CircleOut(CircleCreate):
    """Schema for representing a circle in API responses."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    owner_id: PyObjectId
    member_count: int
    
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

# --- Post Schemas ---

class PostCreate(BaseModel):
    """Schema for creating a new post within a circle."""
    post_type: str = Field(..., example="wishlist_item", description="A string identifying the type of post (e.g., 'text', 'image', 'wishlist_item').")
    content: Dict[str, Any] = Field(..., example={"item_name": "New Laptop", "url": "http://example.com"}, description="A flexible dictionary to store the post's content, allowing for different post structures.")

class PostOut(PostCreate):
    """Schema for representing a post in API responses."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    circle_id: PyObjectId
    author_id: PyObjectId
    author_username: str
    created_at: datetime
    
    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True

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

async def get_circle_or_404(circle_id: str) -> Dict:
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
    circle: Dict = Depends(get_circle_or_404)
) -> Dict:
    """
    A dependency that verifies if the current user is allowed to access a circle.
    
    It first uses `get_circle_or_404` to fetch the circle. Then, it checks:
    1. If the circle is public, access is granted.
    2. If the circle is private, it checks if the current user is in the member list.
    
    If access is denied, it raises an HTTP 403 Forbidden error.

    Returns:
        The circle dictionary if access is permitted.
    """
    # If the circle is public, anyone can access it.
    if circle["is_public"]:
        return circle
        
    # If it's private, check if the user is a member.
    if not any(member['user_id'] == current_user.id for member in circle.get('members', [])):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this circle")
        
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
    
    **Example Usage (curl):**
    ```bash
    curl -X POST "[http://127.0.0.1:8000/auth/register](http://127.0.0.1:8000/auth/register)" \
    -H "Content-Type: application/json" \
    -d '{"username": "testuser", "password": "a-secure-password"}'
    ```
    """
    if users_collection.find_one({"username": user_data.username}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
        
    hashed_password = pwd_context.hash(user_data.password)
    new_user_doc = {"username": user_data.username, "password_hash": hashed_password, "following": [], "followers": []}
    
    result = users_collection.insert_one(new_user_doc)
    created_user = users_collection.find_one({"_id": result.inserted_id})
    
    return UserPublicProfile(**created_user, following_count=0, followers_count=0)

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login_for_access_token(form_data: UserAuth):
    """
    Authenticates a user and returns access and refresh tokens.
    
    - Verifies the username and password.
    - If successful, generates and returns JWTs.
    
    **Example Usage (curl):**
    ```bash
    curl -X POST "[http://127.0.0.1:8000/auth/login](http://127.0.0.1:8000/auth/login)" \
    -H "Content-Type: application/json" \
    -d '{"username": "testuser", "password": "a-secure-password"}'
    ```
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
    # Fetch the full public profiles for each user ID in the 'following' list.
    following_users_cursor = users_collection.find({"_id": {"$in": current_user.following}})
    following_users = [
        UserPublicProfile(**u, following_count=len(u.get("following", [])), followers_count=len(u.get("followers", []))) 
        for u in following_users_cursor
    ]
    
    # The `UserInDB` model has a `following` field with ObjectIds.
    # The `UserPrivateProfile` response model also has a `following` field, but it expects a list of `UserPublicProfile` objects.
    # To avoid a Pydantic error from passing two 'following' arguments, we first convert the `current_user` object to a dictionary and remove its original `following` list of ObjectIds.
    user_data = current_user.dict(by_alias=True)
    user_data.pop("following", None)

    # Now we can construct the `UserPrivateProfile` response, providing the enriched list of `UserPublicProfile` objects to its `following` field.
    return UserPrivateProfile(
        **user_data,
        following_count=len(current_user.following),
        followers_count=len(current_user.followers),
        following=following_users
    )

@app.get("/users", response_model=List[UserPublicProfile], tags=["Users"])
async def list_all_users():
    """Retrieves a list of all public user profiles."""
    users_cursor = users_collection.find({})
    users = [
        UserPublicProfile(**u, following_count=len(u.get("following", [])), followers_count=len(u.get("followers", [])))
        for u in users_cursor
    ]
    return users

@app.get("/users/by-username/{username}", response_model=UserPublicProfile, tags=["Users"])
async def get_user_by_username(username: str):
    """
    Fetches the public profile of a user by their username.
    """
    user = users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    return UserPublicProfile(
        **user,
        following_count=len(user.get("following", [])),
        followers_count=len(user.get("followers", []))
    )

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
    
    # Use MongoDB's '$addToSet' to add the user ID only if it doesn't already exist.
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

    # Use MongoDB's '$pull' to remove the user ID from the arrays.
    users_collection.update_one({"_id": current_user.id}, {"$pull": {"following": target_user["_id"]}})
    users_collection.update_one({"_id": target_user["_id"]}, {"$pull": {"followers": current_user.id}})

# --- Circle Endpoints ---

@app.get("/circles", response_model=List[CircleOut], tags=["Circles"])
async def list_all_circles():
    """
    Retrieves a list of all circles, sorted by creation date.
    
    Note: In a real-world app, you would likely implement pagination for this endpoint.
    """
    # `.sort("created_at", -1)` sorts the results in descending order by creation time.
    circles_cursor = circles_collection.find({}).sort("created_at", -1)
    return [
        CircleOut(**c, member_count=len(c.get("members", []))) for c in circles_cursor
    ]

@app.post("/circles", response_model=CircleOut, status_code=status.HTTP_201_CREATED, tags=["Circles"])
async def create_circle(circle_data: CircleCreate, current_user: UserInDB = Depends(get_current_user)):
    """
    Creates a new circle.
    
    - The user who creates the circle automatically becomes its first member and admin.
    
    **Requires Authentication.**
    """
    # The creator is automatically the admin.
    first_member = CircleMember(user_id=current_user.id, username=current_user.username, role=RoleEnum.admin)
    
    new_circle_doc = {
        "name": circle_data.name, 
        "description": circle_data.description, 
        "is_public": circle_data.is_public,
        "owner_id": current_user.id, 
        "members": [first_member.dict(by_alias=True)], # Pydantic model to dict for DB
        "created_at": datetime.now(timezone.utc)
    }
    
    result = circles_collection.insert_one(new_circle_doc)
    created_circle = circles_collection.find_one({"_id": result.inserted_id})
    
    return CircleOut(**created_circle, member_count=1)

@app.get("/circles/{circle_id}", response_model=CircleOut, tags=["Circles"])
async def get_circle_details(circle: Dict = Depends(check_circle_membership)):
    """
    Retrieves the details for a specific circle.
    
    - Access is controlled by the `check_circle_membership` dependency.
    
    **Requires Authentication for private circles.**
    """
    # The `check_circle_membership` dependency already fetches the circle and
    # validates permissions. We just need to format and return it.
    return CircleOut(**circle, member_count=len(circle.get("members", [])))

# --- Post Endpoints ---

@app.post("/circles/{circle_id}/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED, tags=["Posts"])
async def create_post_in_circle(post_data: PostCreate, circle: Dict = Depends(check_circle_membership), current_user: UserInDB = Depends(get_current_user)):
    """
    Creates a new post within a specific circle.
    
    - The user must be a member of the circle to post.
    
    **Requires Authentication.**
    """
    # The `check_circle_membership` dependency ensures the user has permission.
    new_post = {
        "circle_id": circle["_id"], 
        "author_id": current_user.id, 
        "author_username": current_user.username, 
        "post_type": post_data.post_type, 
        "content": post_data.content, 
        "created_at": datetime.now(timezone.utc)
    }
    result = posts_collection.insert_one(new_post)
    created_post = posts_collection.find_one({"_id": result.inserted_id})
    return PostOut(**created_post)

@app.get("/circles/{circle_id}/posts", response_model=List[PostOut], tags=["Posts"])
async def get_posts_from_circle(circle: Dict = Depends(check_circle_membership)):
    """
    Retrieves all posts from a specific circle, sorted by creation date.
    
    - Access is controlled by the `check_circle_membership` dependency.
    
    **Requires Authentication for private circles.**
    """
    # Use the validated circle object from the dependency to get the ID for the query.
    posts_cursor = posts_collection.find({"circle_id": circle["_id"]}).sort("created_at", -1)
    return [PostOut(**post) for post in posts_cursor]

@app.delete("/circles/{circle_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Posts"])
async def delete_post(circle_id: str, post_id: str, current_user: UserInDB = Depends(get_current_user), circle: Dict = Depends(get_circle_or_404)):
    """
    Deletes a post from a circle.
    
    - A user can delete their own post.
    - A moderator or admin of the circle can delete any post in the circle.
    
    **Requires Authentication.**
    """
    # Validate the post ID format.
    if not ObjectId.is_valid(post_id): 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Post ID")
        
    # Find the post and ensure it belongs to the specified circle.
    post = posts_collection.find_one({"_id": ObjectId(post_id), "circle_id": ObjectId(circle_id)})
    if not post: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found in this circle")
        
    # Check user's role in the circle.
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)
    
    # Determine permissions.
    user_is_mod_or_admin = member_info and RoleEnum(member_info['role']) in [RoleEnum.moderator, RoleEnum.admin]
    user_is_author = post['author_id'] == current_user.id
    
    # If the user is neither the author nor a mod/admin, deny permission.
    if not user_is_author and not user_is_mod_or_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to delete this post")
        
    posts_collection.delete_one({"_id": ObjectId(post_id)})
    # A 204 No Content response does not have a body.
    return

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
    # For this simple setup, we always return the main entry point of the frontend app.
    # In a more complex setup, you might first check if a specific static file
    # exists at `static/{full_path}` and serve it, otherwise fall back to index.html.
    return "static/index.html"


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
