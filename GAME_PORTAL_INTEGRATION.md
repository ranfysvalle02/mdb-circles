# Game Portal Auto-Join Integration Guide

## Problem
When users click "Create Game" or "Join Game" from myCircles, the Game Portal opens with the correct URL parameters (`?game=GAMEID&player_id=PLAYERID`), but the Game Portal frontend doesn't automatically detect these parameters and join the game. Instead, it shows the generic create/join interface.

## Solution
Add the auto-join script to the Game Portal's frontend to automatically detect URL parameters and join the game.

## Integration Steps

### 1. Add the Auto-Join Script to Game Portal

Add the `game_portal_auto_join.js` script to your Game Portal's `index.html` template:

```html
<!-- In your Game Portal's templates/index.html -->
<!DOCTYPE html>
<html>
<head>
    <!-- ... existing head content ... -->
</head>
<body>
    <!-- ... existing body content ... -->
    
    <!-- Add this script BEFORE your main game portal JavaScript -->
    <script src="/static/game_portal_auto_join.js"></script>
    
    <!-- Or inline it: -->
    <script>
        // Paste the contents of game_portal_auto_join.js here
    </script>
    
    <!-- ... rest of your scripts ... -->
</body>
</html>
```

### 2. Alternative: Add to Existing JavaScript File

If you have a main JavaScript file for the Game Portal, you can add the auto-join logic there:

```javascript
// In your main Game Portal JavaScript file
(function() {
    // Check for URL parameters on page load
    const urlParams = new URLSearchParams(window.location.search);
    const gameId = urlParams.get('game');
    const playerId = urlParams.get('player_id');

    if (gameId && playerId) {
        // Hide generic interface
        // Show loading state
        // Auto-join the game
        // (Use the code from game_portal_auto_join.js)
    }
})();
```

### 3. Customize for Your Game Portal Structure

The provided script includes fallback logic, but you may need to customize it based on your Game Portal's actual structure:

1. **WebSocket Connection**: If your Game Portal has a specific WebSocket connection function, update the `connectToGame()` function to use it.

2. **Game Lobby Display**: If your Game Portal has a function to show the game lobby, update the `connectToGame()` function to call it.

3. **UI Elements**: Update the selectors in `hideGenericInterface()` to match your actual HTML structure.

### 4. Testing

After adding the script:

1. Create a game from myCircles
2. The Game Portal should automatically:
   - Hide the generic create/join interface
   - Show a loading state
   - Join the game via API
   - Connect via WebSocket
   - Show the game lobby

## How It Works

1. **URL Parameter Detection**: On page load, checks for `game` and `player_id` URL parameters
2. **Auto-Join**: If parameters are present, automatically calls the join API endpoint
3. **WebSocket Connection**: Establishes WebSocket connection to the game
4. **UI Update**: Hides generic interface and shows game lobby

## API Endpoints Used

- `POST /backend/api/game/{game_id}/join` - Join the game
- `GET /backend/api/game/{game_id}` - Get game information
- `WS /ws/game/{game_id}/{player_id}` - WebSocket connection

## Notes

- The script handles errors gracefully and shows user-friendly error messages
- It works with both HTTP and HTTPS (automatically uses WSS for HTTPS)
- The script is non-intrusive and won't affect normal Game Portal usage when URL parameters aren't present

---

## MyCircles-Specific Endpoints

For seamless integration with MyCircles, use these dedicated endpoints that simplify the game lobby workflow.

### 8. MyCircles Quick Join Endpoint

**Endpoint:** `POST /mycircles/join/{circle_id}/{game_type}`

**Description:** One-liner for MyCircles integration. Gets/creates the persistent lobby for a circle and game type, joins the player automatically, and returns a redirect URL.

**Request:**
```json
{
  "player_id": "unique_player_id"
}
```

**Response:**
```json
{
  "game_id": "game_12345",
  "redirect_url": "https://apps.oblivio-company.com/experiments/game_portal?game=game_12345&replace_placeholder=true",
  "player_count": 2,
  "action": "joined"
}
```

**Features:**
- One lobby per circle per game type (stable lobby IDs based on `circle_id + game_type` hash)
- Persistent lobbies (always exist, can have 0-4 players)
- Auto-join (player joins automatically if not already in lobby)
- Redirect URL (ready-to-use URL for redirecting to the game portal)
- No placeholders (clean player list, no placeholder players)

**Example Usage:**
```javascript
// When user clicks "Play Blackjack" in a circle
async function playGameInCircle(circleId, gameType, userId) {
  const response = await fetch(
    `https://apps.oblivio-company.com/experiments/game_portal/backend/mycircles/join/${circleId}/${gameType}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: userId })
    }
  );
  
  const result = await response.json();
  
  // Automatically redirect to game portal
  window.location.href = result.redirect_url;
}
```

### 9. MyCircles Get Lobby Status Endpoint

**Endpoint:** `GET /mycircles/lobby/{circle_id}/{game_type}`

**Description:** Get lobby status without joining. Use to show "X players waiting" in the UI.

**Response:**
```json
{
  "circle_id": "circle_12345",
  "game_type": "blackjack",
  "player_count": 2,
  "can_join": true,
  "game_id": "game_12345",
  "status": "waiting"
}
```

**Status Values:**
- `"waiting"` - Lobby exists and is waiting for players
- `"full"` - Lobby has 4 players (maximum)
- `"in_progress"` - Game has started (game_id is set)

**Example Usage:**
```javascript
// Show "X players waiting" in circle UI
async function displayLobbyStatus(circleId, gameType) {
  const lobby = await fetch(
    `https://apps.oblivio-company.com/experiments/game_portal/backend/mycircles/lobby/${circleId}/${gameType}`
  ).then(r => r.json());
  
  if (lobby.status === 'waiting') {
    console.log(`${lobby.player_count} players waiting`);
  } else if (lobby.status === 'full') {
    console.log('Lobby is full');
  } else if (lobby.status === 'in_progress') {
    console.log('Game in progress');
  }
}
```

### Integration Workflow

**Complete Example:**
```javascript
class GamePortalClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl || 'https://apps.oblivio-company.com/experiments/game_portal/backend';
  }
  
  // Quick join - one-liner for MyCircles integration
  async joinGame(circleId, gameType, playerId) {
    const response = await fetch(
      `${this.baseUrl}/mycircles/join/${circleId}/${gameType}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_id: playerId })
      }
    );
    
    if (!response.ok) {
      throw new Error(`Failed to join game: ${response.status}`);
    }
    
    return await response.json();
  }
  
  // Get lobby status without joining
  async getLobbyStatus(circleId, gameType) {
    const response = await fetch(
      `${this.baseUrl}/mycircles/lobby/${circleId}/${gameType}`
    );
    
    if (!response.ok) {
      throw new Error(`Failed to get lobby status: ${response.status}`);
    }
    
    return await response.json();
  }
}

// Usage
const client = new GamePortalClient();

// Display lobby status in UI
const status = await client.getLobbyStatus('circle_123', 'blackjack');
console.log(`${status.player_count} players waiting`);

// Join game when user clicks "Play"
const result = await client.joinGame('circle_123', 'blackjack', 'user_456');
window.location.href = result.redirect_url;
```

### Key Features

- **One lobby per circle per game type**: Stable lobby IDs based on `circle_id + game_type` hash
- **Persistent lobbies**: Always exist, can have 0-4 players
- **Auto-join**: Player joins automatically if not already in lobby
- **Redirect URL**: Ready-to-use URL for redirecting to the game portal
- **No placeholders**: Clean player list, no placeholder players
- **Auto-fill on start**: Missing players are filled with AI when the game starts

The system ensures one lobby per circle per game type. When a user clicks "Play Blackjack" in a circle, they join the same lobby as other players in that circle.

