import pymongo
from pymongo import MongoClient
from passlib.context import CryptContext
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import random

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
MONGO_DETAILS = "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
client = MongoClient(MONGO_DETAILS)
db = client.circles_app

users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
follow_requests_collection = db.get_collection("follow_requests")
follow_tokens_collection = db.get_collection("follow_tokens")
chat_messages_collection = db.get_collection("chat_messages")
invite_tokens_collection = db.get_collection("invite_tokens")

# ==============================================================================
# 2. SEEDING LOGIC
# ==============================================================================

def seed_data():
    """Clears and populates the database with realistic demo content."""
    
    print("🔥 Clearing existing data...")
    users_collection.delete_many({})
    circles_collection.delete_many({})
    posts_collection.delete_many({})
    follow_requests_collection.delete_many({})
    follow_tokens_collection.delete_many({})
    chat_messages_collection.delete_many({})
    invite_tokens_collection.delete_many({})
    print("✅ Collections cleared.")

    # --- Create Users ---
    print("\n🌱 Seeding users...")
    users_to_create = [
        {"username": "alice", "password": "password123"},
        {"username": "bob", "password": "password123"},
        {"username": "charlie", "password": "password123"},
        {"username": "diana", "password": "password123"},
        {"username": "eve", "password": "password123"}, 
    ]
    
    user_docs = []
    for user_data in users_to_create:
        user_docs.append({
            "username": user_data["username"],
            "password_hash": pwd_context.hash(user_data["password"]),
            "following": [],
            "followers": []
        })
    users_collection.insert_many(user_docs)
    
    all_users_cursor = users_collection.find({})
    users = {u['username']: u for u in all_users_cursor}
    user_ids = list(users.values())
    print(f"✅ Created {len(users)} users.")

    # --- Establish Pre-approved Follows ---
    print("\n🤝 Seeding pre-approved follow relationships...")
    users_collection.update_one({"_id": users['bob']['_id']}, {"$addToSet": {"following": users['alice']['_id']}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['bob']['_id']}})
    
    users_collection.update_one({"_id": users['charlie']['_id']}, {"$addToSet": {"following": {"$each": [users['alice']['_id'], users['bob']['_id']]}}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['charlie']['_id']}})
    users_collection.update_one({"_id": users['bob']['_id']}, {"$addToSet": {"followers": users['charlie']['_id']}})
    
    users_collection.update_one({"_id": users['diana']['_id']}, {"$addToSet": {"following": users['alice']['_id']}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['diana']['_id']}})
    print("✅ Pre-approved follows created.")

    # --- Create a Pending Follow Request ---
    print("\n⏳ Seeding a pending follow request...")
    follow_requests_collection.insert_one({
        "requester_id": users['eve']['_id'],
        "recipient_id": users['alice']['_id'],
        "created_at": datetime.now(timezone.utc)
    })
    print("✅ Pending request from 'eve' to 'alice' created.")
    
    # --- Create Circles ---
    print("\n🎨 Seeding circles with members...")
    circles_to_create = [
        {"name": "Wanderlust Wishlist", "description": "A public circle for sharing travel dreams and bucket list destinations.", "is_public": True, "owner_id": users['alice']['_id'], "members": [{"user_id": users['alice']['_id'], "username": "alice", "role": "admin"}, {"user_id": users['bob']['_id'], "username": "bob", "role": "moderator"}, {"user_id": users['charlie']['_id'], "username": "charlie", "role": "member"}]},
        {"name": "Media Club", "description": "A private space for discussing our favorite movies, shows, and videos.", "is_public": False, "owner_id": users['bob']['_id'], "members": [{"user_id": users['bob']['_id'], "username": "bob", "role": "admin"}, {"user_id": users['diana']['_id'], "username": "diana", "role": "member"}, {"user_id": users['alice']['_id'], "username": "alice", "role": "member"}]},
        {"name": "Tech & Gadgets", "description": "Latest news, reviews, and discussions on all things tech.", "is_public": True, "owner_id": users['charlie']['_id'], "members": [{"user_id": users['charlie']['_id'], "username": "charlie", "role": "admin"}, {"user_id": users['diana']['_id'], "username": "diana", "role": "moderator"}, {"user_id": users['bob']['_id'], "username": "bob", "role": "member"}]},
        {"name": "Secret Book Club", "description": "Shhh... it's a secret. Password is 'bookworm'.", "is_public": True, "owner_id": users['diana']['_id'], "password_hash": pwd_context.hash("bookworm"), "members": [{"user_id": users['diana']['_id'], "username": "diana", "role": "admin"}]}
    ]
    circles_collection.insert_many(circles_to_create)
    all_circles_cursor = circles_collection.find({})
    circles = {c['name']: c for c in all_circles_cursor}
    print("✅ Circles created (including a password-protected one).")

    # --- Create Posts ---
    print("\n📝 Seeding posts with diverse content...")
    posts_to_create = []
    # Add a YouTube Playlist Post
    playlist_post = {
        "circle_id": circles['Media Club']['_id'], "author_id": users['alice']['_id'], "author_username": 'alice',
        "content": {
            "post_type": "yt-playlist", "tags": ["music", "chill", "focus"],
            "playlist_data": {
                "name": "Lofi Beats to Study To",
                "videos": [
                    {"id": "5qap5aO4i9A", "title": "lofi hip hop radio - beats to relax/study to", "imageSrc": "https://i.ytimg.com/vi/5qap5aO4i9A/hq720.jpg"},
                    {"id": "jfKfPfyJRdk", "title": "lofi hip hop radio - beats to sleep/chill to", "imageSrc": "https://i.ytimg.com/vi/jfKfPfyJRdk/hq720.jpg"}
                ]
            }
        }, "upvotes": [users['diana']['_id'], users['bob']['_id']], "downvotes": [],
        "created_at": datetime.now(timezone.utc) - timedelta(days=2)
    }
    posts_to_create.append(playlist_post)

    # Add Standard Posts
    for i in range(30): # Create more posts for pagination testing
        circle_name = random.choice(list(circles.keys()))
        chosen_circle = circles[circle_name]
        if not chosen_circle['members']: continue
        member = random.choice(chosen_circle['members'])
        author = users[member['username']]
        
        post_content = {}
        if circle_name == "Wanderlust Wishlist":
            post_content = {"link": "https://example.com/travel", "text": "Dreaming of my next adventure to " + random.choice(["Patagonia", "the Amazon", "Tokyo"]) + "! ✈️", "tags": ["travel", "wanderlust", "adventure", "bucketlist"]}
        elif circle_name == "Media Club":
            post_content = {"link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "text": "Just finished watching a new series. Mind blown! 🤯 We need to discuss.", "tags": ["movies", "tvshows", "recommendation"]}
        elif circle_name == "Secret Book Club":
            post_content = {"text": "Just finished '" + random.choice(["Dune", "Project Hail Mary", "The Three-Body Problem"]) + "'. What a ride! Who's read it?", "tags": ["books", "sci-fi", "reading"]}
        else: # Tech & Gadgets
             post_content = {"link": "https://example.com/tech", "text": "What does everyone think about the latest " + random.choice(["Smartphone", "Laptop", "AI advancements"]) + "?", "tags": ["tech", "gadgets", "news"]}
        
        post_content["post_type"] = "standard"

        # Add random votes to make the 'top' sort interesting
        num_upvotes = random.randint(0, len(user_ids))
        num_downvotes = random.randint(0, len(user_ids) - num_upvotes)
        shuffled_users = random.sample(user_ids, num_upvotes + num_downvotes)
        
        upvoters = [u['_id'] for u in shuffled_users[:num_upvotes]]
        downvoters = [u['_id'] for u in shuffled_users[num_upvotes:]]

        posts_to_create.append({
            "circle_id": chosen_circle["_id"], "author_id": author["_id"], "author_username": author["username"],
            "content": post_content, "upvotes": upvoters, "downvotes": downvoters, "score": 0,
            "created_at": datetime.now(timezone.utc) - timedelta(hours=i*3 + random.randint(1, 12))
        })
    posts_collection.insert_many(posts_to_create)

    # Recalculate scores for all posts
    for post in posts_collection.find():
        score = len(post.get('upvotes', [])) - len(post.get('downvotes', []))
        posts_collection.update_one({'_id': post['_id']}, {'$set': {'score': score}})

    print(f"✅ {len(posts_to_create)} posts created with random votes.")

    print("\n\n🎉 Demo database seeded successfully! 🎉")
    print("You can now run the FastAPI server and test with the following users (password for all is 'password123'):")
    for username in users:
        print(f"- {username}")
    print("\nLog in as 'alice' to see the pending follow request from 'eve'.")
    print("Try joining the 'Secret Book Club' with the password 'bookworm'.")

if __name__ == "__main__":
    try:
        client.admin.command('ping')
        print("MongoDB connection successful.")
        seed_data()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()
        print("\nMongoDB connection closed.")