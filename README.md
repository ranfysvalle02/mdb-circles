# mdb-circles

"Circles"distinct, user-created spaces for contextual sharing.

![](mycircles.png)

---

# Beyond the Feed: It's Time to Bring Back Social Circles

**Social media is broken. Instead of one giant feed, we need spaces built for the real relationships in our lives.**

---

Let's be honest: posting online has become exhausting. We find ourselves trapped between two extremes: the chaotic public square of the main feed and the isolated silo of a direct message. Every post requires a calculation. Is this too personal for my coworkers? Too boring for my college friends? Too niche for my family?

This feeling has a name: **context collapse**. It's the flattening of all our distinct social groups into a single, faceless audience. It forces us to perform a weird, generic version of ourselves, and it's burning us out.

There has to be a better way. What if our platforms were built on a truth we all know intuitively? **We don't have one social life; we have many.** It's time to build software that gets that.

---

### The Vision: From a Single Feed to Many Circles

Circles represents a shift from the monolithic feed to a community-centric model. Instead of broadcasting to the world, users create and join distinct, user-created spaces for contextual sharing. Imagine:

* **Share with Precision.** Post your new apartment wishlist in a "New Home" circle for your family. Create a collaborative YouTube playlist in a "Vacation 2026" circle with friends. Talk shop in a "Dev Team" circle with colleagues. No more self-censorship or awkward oversharing.
* **Kill the Social Anxiety.** When you know exactly who you're talking to, the pressure to maintain a single, perfectly curated persona dissolves. You can be your authentic self in each of your social contexts.
* **Build Real Communities.** This model shifts the focus from passively collecting followers to actively building or joining spaces you care about. It's a move from broadcasting to belonging.

This isn't just a concept; it's a design principle baked directly into our API's architecture. Good code doesn't just work—it expresses the core beliefs of the product.

---

## The Blueprint: How Philosophy Meets the Code

The Circles API is built on a modern, high-performance, and scalable foundation designed to bring this vision to life.

**Core Technology Stack:**

* **FastAPI**: A high-performance Python web framework for building APIs.
* **MongoDB**: A flexible, document-oriented database ideal for social data.
* **Pydantic**: For robust data validation, serialization, and settings management.
* **JWT**: For secure, stateless user authentication and authorization.
* **OpenAI API**: To power intelligent, AI-driven features.
* **Cloudinary**: For cloud-based image storage, optimization, and management.

### The NoSQL Data Model: A Strategic Choice

Our choice of MongoDB is a deliberate strategy to achieve both data integrity and raw speed. We do this by balancing two key techniques: referencing and embedding.

**1. Referencing (The `users` Collection)**
For core entities like users, we use **referencing**. Each user has a single document. Other documents, like posts or comments, refer to this user via their `ObjectId`.

```json
// Example User Document
{
  "_id": ObjectId("..."),
  "username": "alice",
  "password_hash": "$2b$12$..."
}
```

**The Payoff:** This is clean and scalable. If a user changes their username, we only update it in one place (though for performance, we may denormalize it elsewhere).

**2. Embedding (The `circles` Collection)**
For data that is tightly coupled, we **embed** it directly. A user's role (e.g., admin, member) only exists *inside* a specific circle, so that's where we store it.

```json
// Example Circle Document with Embedded Members
{
  "_id": ObjectId("..."),
  "name": "Photography Enthusiasts",
  "owner_id": ObjectId("user_alice"),
  "members": [
    { "user_id": ObjectId("user_alice"), "username": "alice", "role": "admin" },
    { "user_id": ObjectId("user_bob"), "username": "bob", "role": "member", "invited_by": ObjectId("user_alice") }
  ]
}
```

**The Payoff:** Blazing-fast reads. A single query retrieves a circle and its complete member list, eliminating the need for database joins and improving data locality.

**3. Denormalization & Flexibility (The `posts` Collection)**
For feed generation, speed is everything. Here, we use **denormalization**—strategically duplicating data—and embrace MongoDB's flexible schema to store varied post types in a single collection.

```json
// Example "Poll" Post Document
{
  "_id": ObjectId("..."),
  "circle_id": ObjectId("circle_photography"),
  "author_id": ObjectId("user_bob"),
  "author_username": "bob", // Duplicated for speed
  "created_at": ISODate("..."),
  "content": {
    "post_type": "poll",
    "poll_data": {
      "question": "Best time for golden hour photos?",
      "options": [
        { "text": "Sunrise", "votes": [ObjectId("user_alice")] },
        { "text": "Sunset", "votes": [] }
      ]
    },
    "expires_at": ISODate("..."),
    "tags": ["photography", "timing"]
  },
  "comment_count": 0
}
```

**The Payoff:** Instant feed loading and feature flexibility. By copying `author_username`, we avoid extra lookups. By using a generic `content` object, we can store polls, wishlists, playlists, and more in the same collection without schema migrations.

---

### Advanced Features in Action

With this solid data foundation, we can build powerful and intuitive features that feel seamless to the user.

#### 1. AI-Powered Content Creation

To make creating engaging content effortless, we integrated the OpenAI API. Users can type a simple phrase ("a poll about the best time for golden hour photos, sunrise or sunset"), and the API transforms it into a structured poll, which is then validated by Pydantic.

```python
@app.post("/utils/generate-poll-from-text", response_model=PollData, tags=["Utilities"])
async def generate_poll_from_text(request: PollFromTextRequest, ...):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="AI service is not configured.")

    system_prompt = """
    You are an intelligent assistant that converts natural language text into a structured poll.
    You must respond ONLY with a JSON object in the format:
    {"question": "The poll question", "options": [{"text": "Option 1"}, ...]}
    """

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.text}
        ],
        response_format={"type": "json_object"}
    )
    poll_json = json.loads(response.choices[0].message.content)
    # Pydantic handles the validation of the AI's output
    return PollData(**poll_json)
```

#### 2. Secure by Design: Granular Permissions

Role-based access control (RBAC) is crucial. We use FastAPI's **Dependency Injection** system to create a reusable "bouncer" that checks permissions before an endpoint's logic ever runs. This keeps our code clean, secure, and easy to reason about.

```python
# A reusable dependency to check membership and get a user's role
async def get_circle_and_user_role(circle_id: str, current_user: UserInDB = Depends(get_current_user)) -> tuple[dict, RoleEnum]:
    circle = await get_circle_or_404(circle_id)
    member_info = next((m for m in circle.get('members', []) if m['user_id'] == current_user.id), None)

    if not member_info:
        raise HTTPException(status_code=403, detail="You are not a member of this circle.")

    return circle, RoleEnum(member_info['role'])

# In the endpoint, the check runs automatically.
@app.patch("/circles/{circle_id}/members/{user_id}", response_model=CircleManagementOut)
async def update_circle_member_role(
    circle_id: str,
    user_id: str,
    role_data: MemberRoleUpdate,
    current_user: UserInDB = Depends(get_current_user)
):
    # This dependency acts as a gatekeeper
    circle, user_role = await get_circle_and_user_role(circle_id, current_user)
    
    # If the code reaches here, the user is a verified member.
    # Now, we just check if their role is high enough.
    if user_role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only an admin can change roles.")
    # ... proceed with update logic
```

#### 3. Fostering Conversation, Not Chaos

To avoid chaotic comment sections, we designed a unique threading system that encourages direct conversation between the post's author and commenters.

* A non-author's first comment creates a **new thread**, identified by their `user_id`.
* The post's author **cannot create new threads**; they can only reply to existing ones.

This creates clean, isolated conversation channels for each commenter with the author.

```python
# From the POST /posts/{post_id}/comments endpoint
@app.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment_on_post(post_id: str, comment_data: CommentCreate, current_user: UserInDB = Depends(get_current_user)):
    post = await get_post_and_check_membership(post_id, current_user)
    is_author = current_user.id == post["author_id"]

    if is_author:
        # Author MUST reply to a specific user's thread.
        if not comment_data.thread_user_id:
            raise HTTPException(
                status_code=403,
                detail="Post authors can only reply to another user's thread."
            )
        thread_id = comment_data.thread_user_id
    else:
        # A non-author's comment always belongs to their own thread.
        thread_id = current_user.id
    
    # ... logic to insert comment with the correct thread_id
```

#### 4. Community Self-Governance: Democratic Kicking

To empower communities, we implemented a democratic kick proposal system. Any member can propose to kick another, which initiates a 48-hour vote. This avoids unilateral decisions by moderators and fosters a sense of shared ownership.

```python
# Pydantic model for a kick proposal
class KickProposalOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    circle_id: PyObjectId
    target_user_id: PyObjectId
    reason: Optional[str] = None
    yes_votes: List[PyObjectId] = []
    no_votes: List[PyObjectId] = []
    expires_at: datetime
    result: Optional[str] = None
```

The backend logic handles vote tallying, expiration, and executing the kick if the proposal passes, providing a robust mechanism for community moderation.

---

### Performance at Scale

A social platform lives and dies by its performance. Our architecture is optimized for speed.

**MongoDB Aggregation Pipelines**
We use MongoDB's aggregation framework to perform complex data shaping and calculations directly within the database, minimizing data transfer. Our feed generation pipeline calculates seen counts, poll results, comment counts, and fetches sample user data for "seen by" avatars—all in a single, efficient query.

```python
# A simplified view of the aggregation pipeline
def _get_posts_aggregation_pipeline(match_stage: dict, ..., current_user: Optional[UserInDB]):
    pipeline = [
        match_stage,
        # Dynamically add fields like counts and user-specific states
        {"$addFields": {
            "seen_by_count": {"$size": {"$ifNull": ["$seen_by_details", []]}},
            "is_seen_by_user": {"$in": [current_user.id, "$seen_by_details.user_id"]},
            "comment_count": {"$ifNull": ["$comment_count", 0]}
        }},
        # Calculate poll results on-the-fly for the requesting user
        {"$addFields": {
            "poll_results": {
                "$cond": {
                    "if": {"$eq": ["$content.post_type", "poll"]},
                    "then": { /* ... complex logic to calculate votes ... */ },
                    "else": "$$REMOVE"
                }
            }
        }},
        # ... additional stages for lookups, sorting, and pagination
    ]
    return pipeline
```

**Strategic Database Indexing**
Proper indexing is non-negotiable. At application startup, we programmatically ensure that indexes exist on all critical query paths to guarantee fast lookups.

```python
# From the lifespan context manager, running at startup
from pymongo import ASCENDING, DESCENDING, IndexModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensures fast lookups for logins
    users_collection.create_index([("username", ASCENDING)], unique=True)
    # Critical for fetching a circle's feed
    posts_collection.create_index([("circle_id", ASCENDING)])
    # Speeds up sorting feeds by time
    posts_collection.create_index([("created_at", DESCENDING)])
    # Index for filtering posts by tags
    posts_collection.create_index([("content.tags", ASCENDING)])
    # Speeds up fetching comment threads
    comments_collection.create_index([("post_id", ASCENDING)])
    # TTL indexes to automatically delete expired tokens and proposals
    invite_tokens_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    kick_proposals_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    print("Database indexes ensured.")
    yield
```

---

### Conclusion: More Than an API, a Better Way to Connect

The Circles API is more than a collection of endpoints; it's a blueprint for building modern, community-centric social applications. By combining a thoughtful social philosophy with a robust technical architecture, we've created a backend that is scalable, feature-rich, and a pleasure to develop on.

The future of social media isn't another billion-user network. It's millions of thriving, context-rich communities. It's time we built the tools to support them.

---

### Appendix: Core Pydantic Models

Key `...Out` models that define the primary data structures returned by the API.

```python
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, Any, List

# A helper class to handle MongoDB's ObjectId in Pydantic models.
# It validates ObjectId strings and ensures they serialize back to strings.
class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any):
        # ... validation and serialization logic ...
        pass

class CircleOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    description: Optional[str]
    owner_id: PyObjectId
    member_count: int
    is_password_protected: bool
    user_role: Optional[str] = None
    
    model_config = ConfigDict(populate_by_name=True)

class PostOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    circle_id: PyObjectId
    circle_name: str
    author_id: PyObjectId
    author_username: str
    content: dict[str, Any]
    created_at: datetime
    seen_by_count: int = 0
    is_seen_by_user: bool = False
    comment_count: int = 0
    poll_results: Optional[dict] = None
    seen_by_user_objects: Optional[List[dict]] = []
    
    model_config = ConfigDict(populate_by_name=True)
```