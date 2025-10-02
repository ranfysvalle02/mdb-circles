# seed_db.py
import os
import random
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from bson import ObjectId
from dotenv import load_dotenv
from faker import Faker
from passlib.context import CryptContext
from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient

# --- Configuration & Setup ---
load_dotenv()
fake = Faker()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MONGO_DETAILS = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:2717/?retryWrites=true&w=majority&directConnection=true"
)
client = MongoClient(MONGO_DETAILS)
db = client.circles_app

# --- Main Seeding Function ---
def seed_database():
    """
    Clears and seeds the database with a variety of consistent, realistic data.
    """
    print("🚀 Starting database seeding process...")

    # 1. Clean Slate: Drop existing collections for a fresh start
    print("🔥 Clearing existing data...")
    collections_to_drop = [
        "users", "circles", "posts", "comments",
        "invite_tokens", "invitations", "notifications"
    ]
    for collection in collections_to_drop:
        db.drop_collection(collection)
    print("✅ Collections cleared.")

    # 2. Seed Users
    print("👤 Seeding users...")
    users = []
    user_data = [
        {"username": "alice"}, {"username": "bob"}, {"username": "charlie"},
        {"username": "diana"}, {"username": "evan"}, {"username": "frank"}
    ]
    for user_info in user_data:
        user = {
            "_id": ObjectId(),
            # Enforce lowercase usernames to match application logic
            "username": user_info["username"].lower(),
            "password_hash": pwd_context.hash("password123")
        }
        users.append(user)
    db.users.insert_many(users)
    print(f"✅ Created {len(users)} users.")

    # Create a quick lookup map for user objects by username
    user_map = {user["username"]: user for user in db.users.find()}

    # 3. Seed Circles
    print("🌐 Seeding circles...")
    alice_id = user_map["alice"]["_id"]
    bob_id = user_map["bob"]["_id"]
    charlie_id = user_map["charlie"]["_id"]
    diana_id = user_map["diana"]["_id"]
    evan_id = user_map["evan"]["_id"]
    frank_id = user_map["frank"]["_id"]

    tech_members = [
        {"user_id": alice_id, "username": "alice", "role": "admin"},
        {"user_id": bob_id, "username": "bob", "role": "moderator"},
        {"user_id": charlie_id, "username": "charlie", "role": "member"}
    ]
    circle_tech = {
        "_id": ObjectId(), "name": "Tech Talk",
        "description": fake.sentence(nb_words=10),
        "owner_id": alice_id, "members": tech_members,
        "created_at": fake.past_datetime(start_date="-30d", tzinfo=timezone.utc)
    }

    book_members = [
        {"user_id": diana_id, "username": "diana", "role": "admin"},
        {"user_id": alice_id, "username": "alice", "role": "member"},
        {"user_id": evan_id, "username": "evan", "role": "member"},
        {"user_id": frank_id, "username": "frank", "role": "member"}
    ]
    circle_books = {
        "_id": ObjectId(), "name": "Book Club",
        "description": fake.sentence(nb_words=8),
        "owner_id": diana_id, "members": book_members,
        "created_at": fake.past_datetime(start_date="-30d", tzinfo=timezone.utc)
    }
    db.circles.insert_many([circle_tech, circle_books])
    print("✅ Created 2 circles.")

    # 4. Seed Posts & Comments
    print("✍️ Seeding posts and comments...")
    all_posts = []
    all_comments = []

    # --- Posts for Tech Talk ---
    post1_id = ObjectId()
    all_posts.append({
        "_id": post1_id, "circle_id": circle_tech["_id"], "author_id": alice_id, "author_username": "alice",
        "content": {
            "post_type": "standard", "text": fake.paragraph(nb_sentences=4),
            "link": "https://github.com", "tags": ["programming", "opensource"],
        },
        "created_at": fake.past_datetime(start_date="-10d", tzinfo=timezone.utc),
        "seen_by_details": [{"user_id": bob_id, "seen_at": fake.past_datetime(start_date="-5d", tzinfo=timezone.utc)}],
    })
    all_comments.extend([
        {"_id": ObjectId(), "post_id": post1_id, "post_author_id": alice_id, "commenter_id": bob_id, "commenter_username": "bob", "content": fake.sentence(), "created_at": fake.past_datetime(start_date="-9d", tzinfo=timezone.utc), "thread_user_id": bob_id},
        {"_id": ObjectId(), "post_id": post1_id, "post_author_id": alice_id, "commenter_id": alice_id, "commenter_username": "alice", "content": "Thanks!", "created_at": fake.past_datetime(start_date="-8d", tzinfo=timezone.utc), "thread_user_id": bob_id}
    ])

    post2_id = ObjectId()
    all_posts.append({
        "_id": post2_id, "circle_id": circle_tech["_id"], "author_id": bob_id, "author_username": "bob",
        "content": {
            "post_type": "poll", "text": "What's your favorite code editor for web development?",
            "poll_data": {
                "question": "Favorite Code Editor?",
                "options": [
                    {"text": "VS Code", "votes": [charlie_id]},
                    {"text": "Neovim", "votes": [bob_id]},
                    {"text": "JetBrains IDEs", "votes": []},
                ],
            },
            "expires_at": datetime.now(timezone.utc) + timedelta(days=3), "tags": ["development", "poll"],
        },
        "created_at": fake.past_datetime(start_date="-2d", tzinfo=timezone.utc),
        "seen_by_details": [
             {"user_id": alice_id, "seen_at": fake.past_datetime(start_date="-1d", tzinfo=timezone.utc)},
             {"user_id": charlie_id, "seen_at": fake.past_datetime(start_date="-1d", tzinfo=timezone.utc)},
        ],
    })

    # --- Posts for Book Club ---
    post3_id = ObjectId()
    all_posts.append({
        "_id": post3_id, "circle_id": circle_books["_id"], "author_id": diana_id, "author_username": "diana",
        "content": {
            "post_type": "wishlist", "text": "My reading wishlist for the next few months!",
            "wishlist_data": [
                {"url": "https://www.goodreads.com/book/show/18144590-the-three-body-problem", "title": "The Three-Body Problem", "description": fake.sentence(), "image": "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1415428227l/20518872.jpg"},
                {"url": "https://www.goodreads.com/book/show/13496.A_Game_of_Thrones", "title": "A Game of Thrones", "description": fake.sentence(), "image": "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1562726234l/13496.jpg"}
            ],
            "tags": ["scifi", "fantasy", "wishlist"],
        },
        "created_at": fake.past_datetime(start_date="-5d", tzinfo=timezone.utc),
        "seen_by_details": [{"user_id": alice_id, "seen_at": fake.past_datetime(start_date="-1d", tzinfo=timezone.utc)}],
    })

    if all_posts:
        db.posts.insert_many(all_posts)
        print(f"✅ Created {len(all_posts)} posts.")
    if all_comments:
        db.comments.insert_many(all_comments)
        print(f"✅ Created {len(all_comments)} comments.")

    # 5. Seed Invitations & Notifications
    print("✉️ Seeding invitations and notifications...")
    # Create a pending invitation from Alice inviting Diana to Tech Talk
    invitation = {
        "_id": ObjectId(), "circle_id": circle_tech["_id"], "inviter_id": alice_id,
        "invitee_id": diana_id, "status": "pending",
        "created_at": datetime.now(timezone.utc) - timedelta(days=1)
    }
    db.invitations.insert_one(invitation)

    # Create a corresponding notification for Diana
    notification = {
        "_id": ObjectId(), "user_id": diana_id, "type": "invite_received",
        "content": {
            "circle_id": str(circle_tech["_id"]), "circle_name": circle_tech["name"],
            "inviter_username": "alice"
        },
        "is_read": False, "created_at": datetime.now(timezone.utc) - timedelta(days=1)
    }
    db.notifications.insert_one(notification)
    print("✅ Created 1 pending invitation and 1 notification.")


    # 6. Final Data Integrity Pass: Update comment counts on posts
    print("🔄 Syncing post comment counts...")
    comment_counts = defaultdict(int)
    for comment in all_comments:
        comment_counts[comment["post_id"]] += 1

    for post_id, count in comment_counts.items():
        db.posts.update_one({"_id": post_id}, {"$set": {"comment_count": count}})
    print("✅ Comment counts synced.")


    # 7. Ensure Indexes
    # Note: This is good practice for a standalone script, but may be redundant
    # if the FastAPI 'lifespan' function is also creating them.
    print("🔍 Ensuring database indexes exist...")
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.circles.create_index([("name", ASCENDING)])
    db.posts.create_index([("circle_id", ASCENDING), ("created_at", DESCENDING)])
    db.posts.create_index([("content.tags", ASCENDING)])
    db.invite_tokens.create_index([("expires_at", DESCENDING)], expireAfterSeconds=0)
    db.invitations.create_index([("invitee_id", ASCENDING), ("status", ASCENDING)])
    db.comments.create_index([("post_id", ASCENDING), ("created_at", ASCENDING)])
    print("✅ Indexes ensured.")


    print("\n🎉 Database seeding complete! 🎉")
    print("You can log in with: alice, bob, charlie, diana, evan, frank")
    print("The password for all users is: password123")
    print("\n💡 Try logging in as 'diana' to see the pending circle invitation!")


# --- Run the Seeder ---
if __name__ == "__main__":
    try:
        seed_database()
    finally:
        client.close()