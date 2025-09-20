import pymongo
from pymongo import MongoClient
from passlib.context import CryptContext
from bson import ObjectId
from datetime import datetime, timezone

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

# IMPORTANT: Use the same MongoDB details as in your main app
MONGO_DETAILS = "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true"

# IMPORTANT: Use the same password hashing context as in your main app
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

client = MongoClient(MONGO_DETAILS)
db = client.circles_app

# Collections
users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")

# ==============================================================================
# 2. SEEDING LOGIC
# ==============================================================================

def seed_data():
    """Clears existing data and populates the database with demo content."""
    
    print("🔥 Clearing existing data...")
    users_collection.delete_many({})
    circles_collection.delete_many({})
    posts_collection.delete_many({})
    print("✅ Collections cleared.")

    # --- Create Users ---
    print("\n🌱 Seeding users...")
    users_to_create = [
        {"username": "alice", "password": "password123"},
        {"username": "bob", "password": "password123"},
        {"username": "charlie", "password": "password123"},
        {"username": "diana", "password": "password123"},
    ]
    
    user_docs = []
    for user in users_to_create:
        user_docs.append({
            "username": user["username"],
            "password_hash": pwd_context.hash(user["password"]),
            "following": [],
            "followers": []
        })
    users_collection.insert_many(user_docs)
    
    # Fetch created users to get their IDs
    alice = users_collection.find_one({"username": "alice"})
    bob = users_collection.find_one({"username": "bob"})
    charlie = users_collection.find_one({"username": "charlie"})
    diana = users_collection.find_one({"username": "diana"})
    print(f"✅ Created {len(users_to_create)} users.")

    # --- Establish Follows ---
    print("\n🤝 Seeding follow relationships...")
    # Bob follows Alice
    users_collection.update_one({"_id": bob["_id"]}, {"$addToSet": {"following": alice["_id"]}})
    users_collection.update_one({"_id": alice["_id"]}, {"$addToSet": {"followers": bob["_id"]}})
    # Charlie follows Alice and Bob
    users_collection.update_one({"_id": charlie["_id"]}, {"$addToSet": {"following": {"$each": [alice["_id"], bob["_id"]]}}})
    users_collection.update_one({"_id": alice["_id"]}, {"$addToSet": {"followers": charlie["_id"]}})
    users_collection.update_one({"_id": bob["_id"]}, {"$addToSet": {"followers": charlie["_id"]}})
    print("✅ Follows created.")
    
    # --- Create Circles ---
    print("\n🎨 Seeding circles with members...")
    circles_to_create = [
        # A public circle
        {
            "name": "Wanderlust Wishlist",
            "description": "A public circle for sharing travel dreams and bucket list destinations.",
            "is_public": True,
            "owner_id": alice["_id"],
            "members": [
                {"user_id": alice["_id"], "username": "alice", "role": "admin"},
                {"user_id": bob["_id"], "username": "bob", "role": "moderator"},
                {"user_id": charlie["_id"], "username": "charlie", "role": "member"},
            ],
            "created_at": datetime.now(timezone.utc)
        },
        # A private circle
        {
            "name": "Secret Book Club",
            "description": "A private space for discussing our monthly book selections. Shhh!",
            "is_public": False,
            "owner_id": bob["_id"],
            "members": [
                {"user_id": bob["_id"], "username": "bob", "role": "admin"},
                {"user_id": diana["_id"], "username": "diana", "role": "member"},
            ],
            "created_at": datetime.now(timezone.utc)
        }
    ]
    circles_collection.insert_many(circles_to_create)

    # Fetch created circles to get their IDs
    wanderlust_circle = circles_collection.find_one({"name": "Wanderlust Wishlist"})
    book_club_circle = circles_collection.find_one({"name": "Secret Book Club"})
    print("✅ Circles created.")

    # --- Create Posts ---
    print("\n📝 Seeding posts in circles...")
    posts_to_create = [
        {
            "circle_id": wanderlust_circle["_id"],
            "author_id": alice["_id"],
            "author_username": "alice",
            "post_type": "wishlist_item",
            "content": {"item": "See the Northern Lights", "location": "Norway", "priority": "high"},
            "created_at": datetime.now(timezone.utc)
        },
        {
            "circle_id": wanderlust_circle["_id"],
            "author_id": bob["_id"],
            "author_username": "bob",
            "post_type": "text_update",
            "content": {"text": "Just booked my tickets to Japan for the cherry blossom festival! Any recommendations?"},
            "created_at": datetime.now(timezone.utc)
        },
        {
            "circle_id": book_club_circle["_id"],
            "author_id": diana["_id"],
            "author_username": "diana",
            "post_type": "book_review",
            "content": {
                "title": "The Midnight Library",
                "author": "Matt Haig",
                "rating": 4.5,
                "review": "Such a thought-provoking read! Loved the concept."
            },
            "created_at": datetime.now(timezone.utc)
        }
    ]
    posts_collection.insert_many(posts_to_create)
    print("✅ Posts created.")

    print("\n\n🎉 Demo database seeded successfully! 🎉")
    print("You can now run the FastAPI server and test with the following users (password for all is 'password123'):")
    print("- alice\n- bob\n- charlie\n- diana")


# ==============================================================================
# 3. EXECUTION
# ==============================================================================

if __name__ == "__main__":
    try:
        seed_data()
    finally:
        client.close()
