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

