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


# ==============================================================================
# 2. SEEDING LOGIC
# ==============================================================================

def seed_data():
    """Clears and populates the database with demo content."""
    
    print("🔥 Clearing existing data...")
    users_collection.delete_many({})
    circles_collection.delete_many({})
    posts_collection.delete_many({})
    follow_requests_collection.delete_many({}) # Clear follow requests
    follow_tokens_collection.delete_many({})   # Clear expired tokens
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
    print(f"✅ Created {len(users)} users.")

    # --- Establish Pre-approved Follows ---
    print("\n🤝 Seeding pre-approved follow relationships...")
    # Bob follows Alice
    users_collection.update_one({"_id": users['bob']['_id']}, {"$addToSet": {"following": users['alice']['_id']}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['bob']['_id']}})
    
    # Charlie follows Alice and Bob
    users_collection.update_one({"_id": users['charlie']['_id']}, {"$addToSet": {"following": {"$each": [users['alice']['_id'], users['bob']['_id']]}}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['charlie']['_id']}})
    users_collection.update_one({"_id": users['bob']['_id']}, {"$addToSet": {"followers": users['charlie']['_id']}})
    
    # Diana follows Alice
    users_collection.update_one({"_id": users['diana']['_id']}, {"$addToSet": {"following": users['alice']['_id']}})
    users_collection.update_one({"_id": users['alice']['_id']}, {"$addToSet": {"followers": users['diana']['_id']}})
    print("✅ Pre-approved follows created.")

    # --- Create a Pending Follow Request ---
    print("\n⏳ Seeding a pending follow request...")
    # Eve requests to follow Alice
    follow_requests_collection.insert_one({
        "requester_id": users['eve']['_id'],
        "recipient_id": users['alice']['_id'],
        "created_at": datetime.now(timezone.utc)
    })
    print("✅ Pending request from 'eve' to 'alice' created.")
    
    # --- Create Circles ---
    print("\n🎨 Seeding circles with members...")
    circles_to_create = [
        {"name": "Wanderlust Wishlist", "description": "A public circle for sharing travel dreams and bucket list destinations.", "is_public": True, "owner_id": users['alice']['_id'], "members": [{"user_id": users['alice']['_id'], "username": "alice", "role": "admin"}, {"user_id": users['bob']['_id'], "username": "bob", "role": "moderator"}, {"user_id": users['charlie']['_id'], "username": "charlie", "role": "member"}], "created_at": datetime.now(timezone.utc) - timedelta(days=5)},
        {"name": "Media Club", "description": "A private space for discussing our favorite movies, shows, and videos.", "is_public": False, "owner_id": users['bob']['_id'], "members": [{"user_id": users['bob']['_id'], "username": "bob", "role": "admin"}, {"user_id": users['diana']['_id'], "username": "diana", "role": "member"}, {"user_id": users['alice']['_id'], "username": "alice", "role": "member"}], "created_at": datetime.now(timezone.utc) - timedelta(days=4)},
        {"name": "Tech & Gadgets", "description": "Latest news, reviews, and discussions on all things tech.", "is_public": True, "owner_id": users['charlie']['_id'], "members": [{"user_id": users['charlie']['_id'], "username": "charlie", "role": "admin"}, {"user_id": users['diana']['_id'], "username": "diana", "role": "moderator"}, {"user_id": users['bob']['_id'], "username": "bob", "role": "member"}], "created_at": datetime.now(timezone.utc) - timedelta(days=3)}
    ]
    circles_collection.insert_many(circles_to_create)
    all_circles_cursor = circles_collection.find({})
    circles = {c['name']: c for c in all_circles_cursor}
    print("✅ Circles created.")

    # --- Create Posts ---
    print("\n📝 Seeding a large number of posts to test pagination...")
    posts_to_create = []
    for i in range(25):
        circle_name = random.choice(list(circles.keys()))
        chosen_circle = circles[circle_name]
        member = random.choice(chosen_circle['members'])
        author = users[member['username']]
        
        content = {}
        if circle_name == "Wanderlust Wishlist":
            content["link"] = "https://example.com/travel"
            content["text"] = "Dreaming of my next adventure to " + random.choice(["Patagonia", "the Amazon", "Tokyo"]) + "! ✈️"
            content["tags"] = ["travel", "wanderlust", "adventure", "bucketlist"]
        elif circle_name == "Media Club":
            content["link"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            content["text"] = "Just finished watching a new series. Mind blown! 🤯 We need to discuss."
            content["tags"] = ["movies", "tvshows", "recommendation"]
        else: # Tech & Gadgets
             content["link"] = "https://example.com/tech"
             content["text"] = "What does everyone think about the latest " + random.choice(["Smartphone", "Laptop", "AI advancements"]) + "?"
             content["tags"] = ["tech", "gadgets", "news"]

        posts_to_create.append({
            "circle_id": chosen_circle["_id"],
            "author_id": author["_id"],
            "author_username": author["username"],
            "content": content,
            "upvotes": [],
            "downvotes": [],
            "score": 0,
            "created_at": datetime.now(timezone.utc) - timedelta(hours=i*2 + random.randint(1, 5))
        })
    posts_collection.insert_many(posts_to_create)
    print(f"✅ {len(posts_to_create)} posts created.")

    print("\n\n🎉 Demo database seeded successfully! 🎉")
    print("You can now run the FastAPI server and test with the following users (password for all is 'password123'):")
    for username in users:
        print(f"- {username}")
    print("\nLog in as 'alice' to see the pending follow request from 'eve'.")

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