"""
seed_db.py - A script to populate the MongoDB database with realistic demo data for the myCircles app.
"""
import pymongo
from pymongo import MongoClient
from passlib.context import CryptContext
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import random

# 1. Database & Password-Hashing Setup
MONGO_DETAILS = "mongodb://localhost:27017/?retryWrites=true&w=majority&directConnection=true"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

try:
    client = MongoClient(MONGO_DETAILS)
    db = client.circles_app
    client.admin.command('ping')
    print("✅ MongoDB connection successful.")
except pymongo.errors.ConnectionFailure as e:
    print(f"🔥 MongoDB connection failed: {e}")
    exit(1)

# Get all collections
users_collection = db.get_collection("users")
circles_collection = db.get_collection("circles")
posts_collection = db.get_collection("posts")
events_collection = db.get_collection("events")
follow_requests_collection = db.get_collection("follow_requests")


def clear_collections():
    """Wipes all data from the relevant collections."""
    print("🔥 Clearing existing data...")
    collections_to_clear = [
        users_collection,
        circles_collection,
        posts_collection,
        events_collection,
        follow_requests_collection,
        # Legacy collections if they exist
        db.get_collection("follow_tokens"),
        db.get_collection("chat_messages"),
        db.get_collection("invite_tokens")
    ]
    for collection in collections_to_clear:
        collection.delete_many({})
    print("✅ All collections cleared.")


def seed_users():
    """Creates a set of demo users."""
    print("\n🌱 Seeding users...")
    users_data = [
        {"username": "alice",   "password": "password123"},
        {"username": "bob",     "password": "password123"},
        {"username": "charlie", "password": "password123"},
        {"username": "diana",   "password": "password123"},
        {"username": "eve",     "password": "password123"},
        {"username": "frank",   "password": "password123"},
    ]
    user_docs = [{
        "_id": ObjectId(),
        "username": u["username"],
        "password_hash": pwd_context.hash(u["password"]),
        "following": [],
        "followers": []
    } for u in users_data]
    users_collection.insert_many(user_docs)
    print(f"✅ Created {len(user_docs)} users.")
    return {u['username']: u for u in users_collection.find()}


def seed_relationships(users):
    """Creates follow relationships and pending requests."""
    print("\n🤝 Seeding user relationships...")
    # Pre-approved follows
    relationships = {
        'alice': ['bob', 'charlie', 'diana'],
        'bob': ['alice', 'charlie'],
        'charlie': ['diana'],
        'diana': ['alice', 'bob'],
        'frank': ['alice', 'bob', 'charlie', 'diana']
    }
    for follower_name, following_list in relationships.items():
        follower_id = users[follower_name]['_id']
        following_ids = [users[name]['_id'] for name in following_list]
        
        # Update follower's "following" list
        users_collection.update_one(
            {"_id": follower_id},
            {"$addToSet": {"following": {"$each": following_ids}}}
        )
        # Update each followed user's "followers" list
        for followed_id in following_ids:
            users_collection.update_one(
                {"_id": followed_id},
                {"$addToSet": {"followers": follower_id}}
            )
    print("✅ Pre-approved follows created.")

    # Pending follow request
    follow_requests_collection.insert_one({
        "requester_id": users['eve']['_id'],
        "recipient_id": users['alice']['_id'],
        "created_at": datetime.now(timezone.utc)
    })
    print("✅ Pending request from 'eve' to 'alice' created.")


def seed_circles(users):
    """Creates demo circles with members."""
    print("\n🎨 Seeding circles...")
    now = datetime.now(timezone.utc)
    circle_docs = [
        {
            "_id": ObjectId(), "name": "Wanderlust Wishlist",
            "description": "A public circle for sharing travel dreams and bucket list destinations.", "is_public": True,
            "owner_id": users['alice']['_id'], "created_at": now - timedelta(days=10),
            "members": [
                {"user_id": users['alice']['_id'], "username": "alice", "role": "admin"},
                {"user_id": users['bob']['_id'], "username": "bob", "role": "member"},
                {"user_id": users['diana']['_id'], "username": "diana", "role": "member"},
                {"user_id": users['frank']['_id'], "username": "frank", "role": "moderator"},
            ]
        },
        {
            "_id": ObjectId(), "name": "Media Club",
            "description": "A private space for discussing our favorite movies, shows, and videos.", "is_public": False,
            "owner_id": users['bob']['_id'], "created_at": now - timedelta(days=8),
            "members": [
                {"user_id": users['bob']['_id'], "username": "bob", "role": "admin"},
                {"user_id": users['alice']['_id'], "username": "alice", "role": "member"},
                {"user_id": users['charlie']['_id'], "username": "charlie", "role": "member"},
            ]
        },
        {
            "_id": ObjectId(), "name": "Tech & Gadgets",
            "description": "Latest news, reviews, and discussions on all things tech.", "is_public": True,
            "owner_id": users['charlie']['_id'], "created_at": now - timedelta(days=5),
            "members": [
                {"user_id": users['charlie']['_id'], "username": "charlie", "role": "admin"},
                {"user_id": users['diana']['_id'], "username": "diana", "role": "moderator"},
                {"user_id": users['frank']['_id'], "username": "frank", "role": "member"},
            ]
        },
        {
            "_id": ObjectId(), "name": "Secret Book Club",
            "description": "Shhh... it's a secret. Password is 'bookworm'.", "is_public": True,
            "owner_id": users['diana']['_id'], "created_at": now - timedelta(days=3),
            "password_hash": pwd_context.hash("bookworm"),
            "members": [{"user_id": users['diana']['_id'], "username": "diana", "role": "admin"}]
        }
    ]
    circles_collection.insert_many(circle_docs)
    print("✅ Circles created (including a private and a password-protected one).")
    return {c['name']: c for c in circles_collection.find()}


def seed_posts(users, circles):
    """Seeds a variety of post types with random interactions."""
    print("\n📝 Seeding posts with diverse content...")
    now = datetime.now(timezone.utc)
    all_user_ids = [u['_id'] for u in users.values()]
    
    post_docs = []

    # --- Pinned Post ---
    post_docs.append({
        "_id": ObjectId(), "circle_id": circles['Wanderlust Wishlist']['_id'], "author_id": users['frank']['_id'],
        "author_username": 'frank', "is_pinned": True, "created_at": now - timedelta(days=9),
        "content": {
            "post_type": "standard", "text": "📌 **Welcome to the Wishlist!**\n\nShare your ultimate travel goals here. Please be respectful and keep discussions on-topic. Let's explore the world together!",
            "tags": ["welcome", "rules", "announcement"]
        },
        "upvotes": [users['alice']['_id'], users['diana']['_id']], "downvotes": []
    })

    # --- Wishlist Post ---
    post_docs.append({
        "_id": ObjectId(), "circle_id": circles['Wanderlust Wishlist']['_id'], "author_id": users['alice']['_id'],
        "author_username": 'alice', "is_pinned": False, "created_at": now - timedelta(days=2),
        "content": {
            "post_type": "wishlist", "text": "This camera would be perfect for the Northern Lights trip we talked about!", "tags": ["gear", "photography", "aurora"],
            "wishlist_data": {
                "url": "https://www.bhphotovideo.com/c/product/1749841-REG/sony_alpha_a7r_v_mirrorless.html",
                "title": "Sony a7R V Mirrorless Camera",
                "description": "Combining resolution and precision, the Sony a7R V is the mirrorless camera designed for those who crave detail.",
                "image": "https://www.bhphotovideo.com/images/images2500x2500/sony_ilce_7rm5_b_alpha_a7r_v_mirrorless_1731388.jpg"
            }
        },
        "upvotes": [users['bob']['_id'], users['frank']['_id']], "downvotes": []
    })

    # --- Poll Post ---
    post_docs.append({
        "_id": ObjectId(), "circle_id": circles['Tech & Gadgets']['_id'], "author_id": users['charlie']['_id'],
        "author_username": 'charlie', "is_pinned": False, "created_at": now - timedelta(hours=12),
        "content": {
            "post_type": "poll", "tags": ["discussion", "phones", "opinion"],
            "poll_data": {
                "question": "Which foldable phone style is the future?",
                "options": [
                    {"text": "Book Style (like Galaxy Fold)", "votes": [users['frank']['_id'], users['diana']['_id']]},
                    {"text": "Clamshell Style (like Galaxy Flip)", "votes": [users['charlie']['_id']]},
                    {"text": "Neither, flat phones are better!", "votes": []}
                ]
            }
        },
        "upvotes": [users['diana']['_id'], users['frank']['_id']], "downvotes": []
    })
    
    # --- YouTube Playlist Post ---
    post_docs.append({
        "_id": ObjectId(), "circle_id": circles['Media Club']['_id'], "author_id": users['alice']['_id'],
        "author_username": 'alice', "is_pinned": False, "created_at": now - timedelta(days=1),
        "content": {
            "post_type": "yt-playlist", "tags": ["music", "chill", "focus"],
            "playlist_data": {
                "name": "Lofi Beats to Study To",
                "videos": [
                    {"id": "5qap5aO4i9A", "title": "lofi hip hop radio - beats to relax/study to", "imageSrc": "https://i.ytimg.com/vi/5qap5aO4i9A/hq720.jpg"},
                    {"id": "jfKfPfyJRdk", "title": "lofi hip hop radio - beats to sleep/chill to", "imageSrc": "https://i.ytimg.com/vi/jfKfPfyJRdk/hq720.jpg"}
                ]
            }
        },
        "upvotes": [users['bob']['_id'], users['charlie']['_id']], "downvotes": []
    })

    # --- 20 Standard Posts ---
    for i in range(20):
        circle = random.choice(list(circles.values()))
        member = random.choice(circle['members'])
        author = users[member['username']]
        
        post_docs.append({
            "_id": ObjectId(), "circle_id": circle['_id'], "author_id": author['_id'], "author_username": author['username'],
            "is_pinned": False, "created_at": now - timedelta(hours=i * 4 + random.randint(1, 3)),
            "content": {
                "post_type": "standard", "text": f"This is a standard post ({i+1}/20) by {author['username']} in the '{circle['name']}' circle.", "tags": ["general", "discussion"]
            },
            "upvotes": random.sample(all_user_ids, k=random.randint(0, len(all_user_ids))),
            "downvotes": []
        })
    
    for post in post_docs:
        # Prevent users from upvoting their own post or being in both up/down votes
        post_author_id = post['author_id']
        if post_author_id in post['upvotes']: post['upvotes'].remove(post_author_id)
        
        available_downvoters = list(set(all_user_ids) - set(post['upvotes']) - {post_author_id})
        post['downvotes'] = random.sample(available_downvoters, k=random.randint(0, len(available_downvoters)))
        
        post['score'] = len(post['upvotes']) - len(post['downvotes'])
    
    if post_docs:
        posts_collection.insert_many(post_docs)
    print(f"✅ {len(post_docs)} posts seeded.")


def seed_events(users, circles):
    """Seeds upcoming and past events with attendees."""
    print("\n📅 Seeding events...")
    now = datetime.now(timezone.utc)
    event_docs = [
        {
            "_id": ObjectId(), "circle_id": circles['Tech & Gadgets']['_id'], "creator_id": users['diana']['_id'],
            "title": "Tech Conference Watch Party", "description": "Let's watch the keynote live and discuss the new announcements.",
            "start_time": now + timedelta(days=7, hours=3), "end_time": now + timedelta(days=7, hours=5),
            "location": "Online / Circle Chat Room", "attendees": [users['diana']['_id'], users['frank']['_id']]
        },
        {
            "_id": ObjectId(), "circle_id": circles['Wanderlust Wishlist']['_id'], "creator_id": users['frank']['_id'],
            "title": "Planning Session: Southeast Asia Trip", "description": "Let's brainstorm an itinerary for a potential group trip next year!",
            "start_time": now + timedelta(days=12, hours=1), "location": "Zoom (Link to be provided)",
            "attendees": [users['frank']['_id'], users['alice']['_id'], users['diana']['_id']]
        },
        {
            "_id": ObjectId(), "circle_id": circles['Media Club']['_id'], "creator_id": users['bob']['_id'],
            "title": "Movie Night: Retro Sci-Fi", "description": "We watched 'Blade Runner'. The discussion was epic!",
            "start_time": now - timedelta(days=4), "end_time": now - timedelta(days=4, hours=-3),
            "location": "Bob's Place", "attendees": [users['bob']['_id'], users['alice']['_id']]
        }
    ]
    if event_docs:
        events_collection.insert_many(event_docs)
    print(f"✅ {len(event_docs)} events seeded (upcoming and past).")


def main():
    """Main function to run the seeding process."""
    clear_collections()
    seeded_users = seed_users()
    seed_relationships(seeded_users)
    seeded_circles = seed_circles(seeded_users)
    seed_posts(seeded_users, seeded_circles)
    seed_events(seeded_users, seeded_circles)

    print("\n\n🎉 Demo database seeded successfully! 🎉")
    print("Use the following users (password = 'password123'):")
    for username in seeded_users:
        print(f" - {username}")
    print("\n💡 Suggestions:")
    print("  - Log in as 'alice' to see the pending follow request from 'eve'.")
    print("  - Try joining the 'Secret Book Club' with the password 'bookworm'.")
    print("  - Check the 'Tech & Gadgets' circle for an upcoming event.")


if __name__ == "__main__":
    main()
    client.close()
    print("\nMongoDB connection closed.")