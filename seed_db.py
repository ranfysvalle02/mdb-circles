import os
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from bson import ObjectId
from passlib.context import CryptContext
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from .env file
load_dotenv()

# Use the same MongoDB URI and password context as your main application
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "circles_app"  # Make sure this matches your FastAPI app's database name
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Helper Functions ---
def hash_password(password):
    """Hashes a password using the application's context."""
    return pwd_context.hash(password)

def get_utc_now():
    """Returns the current time in a timezone-aware format."""
    return datetime.now(timezone.utc)

# --- Main Seeding Logic ---
def seed_database():
    """
    Clears and populates the database with a complete set of sample data.
    """
    print("--- Starting Database Seeding ---")
    
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")
        return

    # 1. Clear existing data
    print("🗑️ Clearing existing collections...")
    collections_to_clear = [
        "users", "circles", "posts", "comments", 
        "invitations", "notifications", "activity_events", "friends"
    ]
    for collection_name in collections_to_clear:
        db[collection_name].delete_many({})
    print("✅ Collections cleared.")

    # 2. Create Users
    print("\n👤 Creating users...")
    users = {}
    user_data = [
        ("alice", "password123"),
        ("bob", "password123"),
        ("charlie", "password123"),
        ("diana", "password123"),
        ("eve", "password123"),
    ]
    for username, password in user_data:
        user_doc = {
            "username": username,
            "password_hash": hash_password(password),
        }
        result = db.users.insert_one(user_doc)
        users[username] = result.inserted_id
        print(f"   - Created user: {username}")
    print(f"✅ Created {len(users)} users.")

    # 3. Create Circles
    print("\n🌐 Creating circles and adding members...")
    circles = {}
    
    # Circle 1: Cool Coders (Private)
    # Note: Colors, personal_name, and tags are member-specific - each member can have their own values
    coders_circle_doc = {
        "name": "Cool Coders",
        "description": "A private space for discussing development and projects.",
        "owner_id": users["alice"],
        "is_public": False,
        "created_at": get_utc_now(),
        "members": [
            {
                "user_id": users["alice"], 
                "username": "alice", 
                "role": "admin", 
                "color": "#3B82F6",  # Blue for alice
                "personal_name": "Dev Team",  # Alice's personal name for this circle
                "tags": ["work", "development", "coding"]
            },
            {
                "user_id": users["bob"], 
                "username": "bob", 
                "role": "moderator", 
                "color": "#10B981",  # Green for bob
                "personal_name": "Cool Coders",  # Bob uses default (circle name)
                "tags": ["coding", "projects"]
            },
            {
                "user_id": users["charlie"], 
                "username": "charlie", 
                "role": "member", 
                "color": "#F59E0B",  # Orange for charlie
                # No personal_name - will default to circle name
                "tags": ["work"]
            },
        ]
    }
    result = db.circles.insert_one(coders_circle_doc)
    circles["coders"] = result.inserted_id
    print("   - Created circle: Cool Coders")

    # Circle 2: Weekend Gamers (Private)
    # Note: Colors, personal_name, and tags are member-specific - different members see different values
    gamers_circle_doc = {
        "name": "Weekend Gamers",
        "description": "Planning our weekend gaming sessions. All skill levels welcome!",
        "owner_id": users["bob"],
        "is_public": False,
        "created_at": get_utc_now(),
        "members": [
            {
                "user_id": users["bob"], 
                "username": "bob", 
                "role": "admin", 
                "color": "#8B5CF6",  # Purple for bob
                "personal_name": "Gaming Squad",  # Bob's personal name
                "tags": ["gaming", "weekend", "friends"]
            },
            {
                "user_id": users["diana"], 
                "username": "diana", 
                "role": "member", 
                "color": "#EF4444",  # Red for diana
                # No personal_name - will default to circle name
                "tags": ["gaming", "fun"]
            },
            {
                "user_id": users["eve"], 
                "username": "eve", 
                "role": "member", 
                "color": "#06B6D4",  # Cyan for eve
                "personal_name": "Game Night",  # Eve's personal name
                "tags": ["gaming", "social"]
            },
        ]
    }
    result = db.circles.insert_one(gamers_circle_doc)
    circles["gamers"] = result.inserted_id
    print("   - Created circle: Weekend Gamers")

    # Circle 3: Public Square (Public)
    # Note: Colors, personal_name, and tags are member-specific - demonstrates that same circle can have different values per member
    # Some members have colors/personal_names/tags, some don't (to show fallback behavior)
    public_circle_doc = {
        "name": "Public Square",
        "description": "A public circle for everyone to share anything interesting.",
        "owner_id": users["charlie"],
        "is_public": True,
        "created_at": get_utc_now(),
        "members": [
            {
                "user_id": users["charlie"], 
                "username": "charlie", 
                "role": "admin", 
                "color": "#F97316",  # Orange for charlie
                "personal_name": "Public Square",  # Uses default (circle name)
                "tags": ["public", "general", "sharing"]
            },
            {
                "user_id": users["alice"], 
                "username": "alice", 
                "role": "member", 
                "color": "#14B8A6",  # Teal for alice
                "personal_name": "Community Feed",  # Alice's personal name
                "tags": ["community", "sharing"]
            },
            {
                "user_id": users["bob"], 
                "username": "bob", 
                "role": "member", 
                "color": "#EC4899",  # Pink for bob
                # No personal_name - will default to circle name
                "tags": ["public"]
            },
            {
                "user_id": users["diana"], 
                "username": "diana", 
                "role": "member"
                # No color, personal_name, or tags - will use defaults/fallbacks
            },
            {
                "user_id": users["eve"], 
                "username": "eve", 
                "role": "member", 
                "color": "#84CC16",  # Lime for eve
                "personal_name": "Public Discussions",  # Eve's personal name
                "tags": ["public", "discussions", "social"]
            },
        ]
    }
    result = db.circles.insert_one(public_circle_doc)
    circles["public"] = result.inserted_id
    print("   - Created circle: Public Square")
    print(f"✅ Created {len(circles)} circles.")

    # 4. Create Posts
    print("\n📝 Creating posts of various types...")
    posts = {}
    
    # --- Post Definitions ---
    post_definitions = [
        # Standard Posts
        {"author": "alice", "circle": "coders", "content": {"post_type": "standard", "text": "Just pushed a major update to the main branch! Please review my PR. The key file to check is `app/services/new_feature.py`."}},
        {"author": "bob", "circle": "public", "content": {"post_type": "standard", "text": "Has anyone seen the latest Blade Runner movie? Thoughts?", "link": "https://www.imdb.com/title/tt1856101/", "tags": ["movies", "sci-fi"]}},
        
        # Poll Post
        {"author": "bob", "circle": "gamers", "content": {
            "post_type": "poll",
            "poll_data": {
                "question": "What should we play this Friday?",
                "options": [{"text": "Valorant"}, {"text": "Helldivers 2"}, {"text": "Lethal Company"}, {"text": "League of Legends"}]
            },
            "expires_at": get_utc_now() + timedelta(days=3),
            "tags": ["planning", "gaming"]
        }},

        # YouTube Playlist Post
        {"author": "charlie", "circle": "public", "content": {
            "post_type": "yt-playlist",
            "playlist_data": {
                "name": "Chill Lofi Beats to Code/Relax to",
                "videos": [
                    {"id": "5qap5aO4i9A", "title": "lofi hip hop radio 📚 - beats to relax/study to", "imageSrc": "https://i.ytimg.com/vi/5qap5aO4i9A/hqdefault_live.jpg"},
                    {"id": "jfKfPfyJRdk", "title": "lofi hip hop radio 💤 - beats to sleep/chill to", "imageSrc": "https://i.ytimg.com/vi/jfKfPfyJRdk/hqdefault_live.jpg"}
                ]
            },
            "tags": ["music", "focus"]
        }},
        
        # Wishlist Post
        {"author": "diana", "circle": "gamers", "content": {
            "post_type": "wishlist",
            "text": "My PC Upgrade Wishlist!",
            "wishlist_data": [
                {"url": "https://www.amazon.com/dp/B09VCHR1VH", "title": "NVIDIA GeForce RTX 4090"},
                {"url": "https://www.amazon.com/dp/B0BEHH2V26", "title": "AMD Ryzen 9 7950X3D"}
            ]
        }},

        # Image Post
        {"author": "eve", "circle": "public", "content": {
            "post_type": "image",
            "images_data": [{
                "url": "https://res.cloudinary.com/demo/image/upload/sample.jpg",
                "public_id": "sample", "height": 864, "width": 1280,
                "caption": "Found this cool sample image. What a landscape!"
            }],
            "tags": ["photography", "nature"]
        }},
        
        # Spotify Playlist Post
        {"author": "alice", "circle": "public", "content": {
            "post_type": "spotify_playlist",
            "text": "Check out my workout playlist!",
            "spotify_playlist_data": {
                "playlist_name": "Beast Mode",
                "embed_url": "https://open.spotify.com/embed/playlist/?utm_source=generator",
                "spotify_url": "http://googleusercontent.com/spotify.com/6"
            },
            "tags": ["music", "fitness"]
        }},
    ]
    
    for i, p_def in enumerate(post_definitions):
        author_id = users[p_def["author"]]
        circle_id = circles[p_def["circle"]]
        post_doc = {
            "author_id": author_id,
            "author_username": p_def["author"],
            "circle_id": circle_id,
            "content": p_def["content"],
            "created_at": get_utc_now() - timedelta(hours=i*2), # Stagger post times
            "seen_by_details": [],
            "comment_count": 0,
            "is_chat_enabled": False,
        }
        # Add poll votes for the poll post
        if p_def["content"]["post_type"] == "poll":
            post_doc["content"]["poll_data"]["options"][0]["votes"] = [users["diana"]]
            post_doc["content"]["poll_data"]["options"][1]["votes"] = [users["bob"], users["eve"]]

        result = db.posts.insert_one(post_doc)
        posts[f"post_{i+1}"] = result.inserted_id
    
    print(f"✅ Created {len(posts)} posts.")

    # 5. Simulate Post Views and Comments
    print("\n💬 Simulating views and comments...")
    
    # Add views to the first post
    db.posts.update_one(
        {"_id": posts["post_1"]},
        {"$set": {
            "seen_by_details": [
                {"user_id": users["bob"], "seen_at": get_utc_now() - timedelta(minutes=30)},
                {"user_id": users["charlie"], "seen_at": get_utc_now() - timedelta(minutes=15)},
            ]
        }}
    )

    # Add comments
    comment1_doc = {
        "post_id": posts["post_1"], "post_author_id": users["alice"],
        "commenter_id": users["bob"], "commenter_username": "bob",
        "content": "Looks good, Alice! Just left a couple of minor suggestions on the PR.",
        "created_at": get_utc_now() - timedelta(minutes=10),
        "thread_user_id": users["bob"], # Non-author comment, thread is their own
    }
    db.comments.insert_one(comment1_doc)

    comment2_doc = {
        "post_id": posts["post_1"], "post_author_id": users["alice"],
        "commenter_id": users["alice"], "commenter_username": "alice",
        "content": "Thanks for the quick review, Bob! I'll address them now.",
        "created_at": get_utc_now() - timedelta(minutes=5),
        "thread_user_id": users["bob"], # Author replying to Bob's thread
    }
    db.comments.insert_one(comment2_doc)

    # Update comment count on the post
    db.posts.update_one({"_id": posts["post_1"]}, {"$set": {"comment_count": 2}})
    print("✅ Simulated activity on posts.")

    # 6. Create Friendships
    print("\n🤝 Creating friendships based on circle memberships...")
    
    # Build a set of user pairs who are in the same circles
    friend_pairs = set()
    
    # Get all circles to find shared memberships
    all_circles = list(db.circles.find({}))
    for circle in all_circles:
        members = circle.get("members", [])
        member_ids = [member["user_id"] for member in members]
        
        # Create pairs for all members in this circle
        for i in range(len(member_ids)):
            for j in range(i + 1, len(member_ids)):
                # Store pairs in sorted order to avoid duplicates
                pair = tuple(sorted([member_ids[i], member_ids[j]]))
                friend_pairs.add(pair)
    
    print(f"   Found {len(friend_pairs)} unique friend pairs to create.")
    
    # Create bidirectional friendships
    friendships_created = 0
    for user1_id, user2_id in friend_pairs:
        # Get usernames
        user1 = db.users.find_one({"_id": user1_id})
        user2 = db.users.find_one({"_id": user2_id})
        
        if not user1 or not user2:
            continue
        
        user1_username = user1.get("username", "unknown")
        user2_username = user2.get("username", "unknown")
        
        # Check if friendship already exists
        existing = db.friends.find_one({
            "user_id": user1_id,
            "friend_id": user2_id
        })
        
        if not existing:
            now = get_utc_now()
            
            # Create bidirectional friendship entries
            # Entry 1: user1 -> user2
            friend_doc_1 = {
                "user_id": user1_id,
                "friend_id": user2_id,
                "username": user2_username,
                "status": "accepted",
                "created_at": now,
                "requested_by": user1_id
            }
            db.friends.insert_one(friend_doc_1)
            
            # Entry 2: user2 -> user1
            friend_doc_2 = {
                "user_id": user2_id,
                "friend_id": user1_id,
                "username": user1_username,
                "status": "accepted",
                "created_at": now,
                "requested_by": user1_id
            }
            db.friends.insert_one(friend_doc_2)
            
            friendships_created += 1
            print(f"   - Created friendship: {user1_username} ↔ {user2_username}")
    
    print(f"✅ Created {friendships_created} friendships ({friendships_created * 2} friend entries total).")

    # --- Finalization ---
    print("\n\n--- Seeding Complete! ---")
    print(f"Database '{DB_NAME}' is now populated with sample data.")
    print(f"   - Users: {len(users)}")
    print(f"   - Circles: {len(circles)}")
    print(f"   - Posts: {len(posts)}")
    print(f"   - Friendships: {friendships_created}")
    client.close()

if __name__ == "__main__":
    seed_database()