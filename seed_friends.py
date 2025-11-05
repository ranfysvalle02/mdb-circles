import os
from datetime import datetime, timezone
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from .env file
load_dotenv()

# Use the same MongoDB URI as your main application
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "circles_app"  # Make sure this matches your FastAPI app's database name

# --- Helper Functions ---
def get_utc_now():
    """Returns the current time in a timezone-aware format."""
    return datetime.now(timezone.utc)

# --- Main Seeding Logic ---
def seed_friends():
    """
    Populates the database with friend relationships based on circle memberships.
    If two users are in the same circle, they automatically become friends.
    """
    print("--- Starting Friends Seeding ---")
    
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")
        return

    # 1. Clear existing friends data (optional - comment out if you want to keep existing friendships)
    print("🗑️ Clearing existing friends collection...")
    db.friends.delete_many({})
    print("✅ Friends collection cleared.")

    # 2. Get all circles
    print("\n🌐 Gathering circle memberships...")
    circles = list(db.circles.find({}))
    print(f"   Found {len(circles)} circles.")
    
    if not circles:
        print("⚠️  No circles found. Skipping friend seeding.")
        client.close()
        return

    # 3. Build a set of user pairs who are in the same circles
    # Using a set to avoid duplicates
    friend_pairs = set()
    
    for circle in circles:
        members = circle.get("members", [])
        member_ids = [member["user_id"] for member in members]
        
        # Create pairs for all members in this circle
        for i in range(len(member_ids)):
            for j in range(i + 1, len(member_ids)):
                # Store pairs in sorted order to avoid duplicates
                pair = tuple(sorted([member_ids[i], member_ids[j]]))
                friend_pairs.add(pair)
        
        circle_name = circle.get("name", "Unknown")
        print(f"   - Processed circle '{circle_name}' with {len(member_ids)} members")

    print(f"\n✅ Found {len(friend_pairs)} unique friend pairs to create.")

    # 4. Get user information for usernames
    print("\n👤 Fetching user information...")
    all_user_ids = set()
    for pair in friend_pairs:
        all_user_ids.update(pair)
    
    users = {}
    for user_id in all_user_ids:
        user = db.users.find_one({"_id": user_id})
        if user:
            users[user_id] = user.get("username", "unknown")
    
    print(f"   Found {len(users)} users.")

    # 5. Create bidirectional friendships
    print("\n🤝 Creating friendships...")
    friendships_created = 0
    
    for user1_id, user2_id in friend_pairs:
        user1_username = users.get(user1_id, "unknown")
        user2_username = users.get(user2_id, "unknown")
        
        # Check if friendship already exists (shouldn't happen after clearing, but just in case)
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
                "requested_by": user1_id  # Auto-accepted, so we'll use user1 as the requester
            }
            db.friends.insert_one(friend_doc_1)
            
            # Entry 2: user2 -> user1
            friend_doc_2 = {
                "user_id": user2_id,
                "friend_id": user1_id,
                "username": user1_username,
                "status": "accepted",
                "created_at": now,
                "requested_by": user1_id  # Same requester for both entries
            }
            db.friends.insert_one(friend_doc_2)
            
            friendships_created += 1
            print(f"   - Created friendship: {user1_username} ↔ {user2_username}")
    
    print(f"\n✅ Created {friendships_created} friendships ({friendships_created * 2} friend entries total).")

    # --- Finalization ---
    print("\n\n--- Friends Seeding Complete! ---")
    print(f"All users who share circles are now friends in database '{DB_NAME}'.")
    client.close()

if __name__ == "__main__":
    seed_friends()

