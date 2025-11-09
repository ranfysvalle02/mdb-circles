# Game Portal Changes Required

## Overview
The Game Portal needs to detect the `game` URL parameter and automatically join the game when users click "Start Game" or "Join Game" from myCircles. The `player_id` is **auto-detected** by the Game Portal backend from the session/authentication, so it should NOT be passed in the URL.

## Required Changes

### 1. Add Auto-Join Script to `templates/index.html`

Add the auto-join script to your Game Portal's `index.html` template. You have two options:

#### Option A: Include as External Script (Recommended)

Add this to your `templates/index.html` **BEFORE** your main Game Portal JavaScript:

```html
<!-- Add this in the <head> or before closing </body> tag -->
<script src="/static/game_portal_auto_join_simple.js"></script>
```

Then copy `game_portal_auto_join_simple.js` to your Game Portal's static files directory.

#### Option B: Inline the Script

Add this directly to your `templates/index.html`:

```html
<script>
// Auto-join script - paste contents of game_portal_auto_join_simple.js here
window.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameId = urlParams.get('game');

    if (!gameId) {
        return; // No auto-join needed
    }

    console.log(`Auto-joining game ${gameId} (player_id will be auto-detected by backend)`);

    // Hide generic interface elements
    const createForm = document.querySelector('#createGameForm, .create-game-form');
    const joinForm = document.querySelector('#joinGameForm, .join-game-form');
    
    if (createForm) createForm.style.display = 'none';
    if (joinForm) joinForm.style.display = 'none';

    // Show loading state
    showLoading(`Joining game ${gameId}...`);

    // Auto-join the game (player_id will be auto-detected by backend from session/auth)
    joinGame(gameId);
});

async function joinGame(gameId) {
    try {
        const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
        const joinUrl = `${baseUrl}/backend/api/game/${gameId}/join`;

        // Get player_id from Game Portal's session/auth (if available)
        // The backend should auto-detect it, but we can try to get it from common places
        let playerId = null;
        if (typeof localStorage !== 'undefined') {
            playerId = localStorage.getItem('player_id') || localStorage.getItem('userId');
        }
        
        const requestBody = {
            replace_ai: null,
            as_spectator: false
        };
        
        // Only include player_id if we found it, otherwise let backend auto-detect
        if (playerId) {
            requestBody.player_id = playerId;
        }

        const response = await fetch(joinUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include', // Include cookies for session/auth
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.error || `HTTP ${response.status}`);
        }

        const result = await response.json();
        
        if (result.error && !result.error.includes('already')) {
            throw new Error(result.error);
        }

        console.log('Successfully joined game:', result);
        hideLoading();

        // Get player_id from response if backend provided it
        const actualPlayerId = result.player_id || playerId;
        
        if (!actualPlayerId) {
            throw new Error('Could not determine player_id. Please ensure you are authenticated.');
        }

        // Connect via WebSocket
        connectWebSocket(gameId, actualPlayerId);

    } catch (error) {
        console.error('Failed to join game:', error);
        hideLoading();
        showError(`Failed to join game: ${error.message}`);
    }
}

function connectWebSocket(gameId, playerId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsPath = window.location.pathname.replace(/\/$/, '') + `/ws/game/${gameId}/${playerId}`;
    const wsUrl = `${protocol}//${window.location.host}${wsPath}`;

    console.log('Connecting to WebSocket:', wsUrl);

    try {
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('WebSocket connected');
            hideLoading();
            // Your Game Portal should handle the rest via WebSocket messages
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            showError('Failed to connect to game. Please refresh the page.');
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            console.log('WebSocket message:', message);
            
            if (message.type === 'connection_success') {
                hideLoading();
                // Game is connected - your Game Portal should show the game interface
            }
        };

        // Store WebSocket globally for your Game Portal to use
        window.gameWebSocket = ws;

    } catch (error) {
        console.error('Failed to create WebSocket:', error);
        showError('Failed to connect to game.');
    }
}

function showLoading(message) {
    const loading = document.createElement('div');
    loading.id = 'auto-join-loading';
    loading.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        z-index: 9999;
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 2rem;
        border-radius: 8px;
    `;
    loading.innerHTML = `
        <div style="font-size: 1.2rem; margin-bottom: 1rem;">${message}</div>
        <div style="border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
    `;
    document.body.appendChild(loading);

    // Add spinner animation
    if (!document.getElementById('spinner-style')) {
        const style = document.createElement('style');
        style.id = 'spinner-style';
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
}

function hideLoading() {
    const loading = document.getElementById('auto-join-loading');
    if (loading) loading.remove();
}

function showError(message) {
    const error = document.createElement('div');
    error.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        z-index: 9999;
        background: rgba(220, 53, 69, 0.9);
        color: white;
        padding: 2rem;
        border-radius: 8px;
        max-width: 400px;
    `;
    error.innerHTML = `
        <div style="font-size: 1.2rem; margin-bottom: 1rem;">⚠️ Error</div>
        <div style="margin-bottom: 1rem;">${message}</div>
        <button onclick="location.reload()" style="padding: 0.5rem 1rem; background: white; color: #dc3545; border: none; border-radius: 4px; cursor: pointer;">
            Refresh Page
        </button>
    `;
    document.body.appendChild(error);
}
</script>
```

### 2. Update Your Game Portal's WebSocket Connection Logic

If your Game Portal already has WebSocket connection logic, you may need to update it to:

1. **Check for existing WebSocket**: If `window.gameWebSocket` exists (from auto-join), use it instead of creating a new one
2. **Handle connection_success message**: When the WebSocket receives `connection_success`, show the game lobby instead of the generic interface

Example integration:

```javascript
// In your existing Game Portal JavaScript
if (window.gameWebSocket) {
    // Use the auto-joined WebSocket
    const ws = window.gameWebSocket;
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        
        if (message.type === 'connection_success') {
            // Hide generic interface
            hideGenericInterface();
            
            // Show game lobby
            showGameLobby(message);
        }
        
        // Handle other WebSocket messages...
    };
} else {
    // Normal WebSocket connection flow
    // (your existing code)
}
```

### 3. Update UI Element Selectors (If Needed)

The auto-join script tries to hide generic interface elements using these selectors:

- `#createGameForm` or `.create-game-form` or `[data-create-form]`
- `#joinGameForm` or `.join-game-form` or `[data-join-form]`

**If your Game Portal uses different selectors**, update the `hideGenericInterface()` function in the auto-join script to match your HTML structure.

### 4. Ensure Game Lobby is Shown After Connection

After the WebSocket connects and receives `connection_success`, your Game Portal should:

1. Hide the generic create/join interface
2. Show the game lobby with:
   - Game ID
   - List of players
   - Game type and mode
   - Start game button (if host)
   - Game state (if game is in progress)

## Testing

After making these changes:

1. **Test from myCircles**:
   - Click "Start Game" from a circle
   - Game Portal should automatically:
     - Hide generic interface
     - Show loading spinner
     - Join the game via API
     - Connect via WebSocket
     - Show game lobby

2. **Test Join from Post**:
   - Click "Join Game" button on a game post
   - Same behavior as above

3. **Test Normal Usage**:
   - Visit Game Portal without URL parameters
   - Should show normal create/join interface (no changes)

## Files to Modify

1. **`templates/index.html`** - Add auto-join script
2. **`static/game_portal_auto_join_simple.js`** - Copy from myCircles repo (optional if using inline)
3. **Your main Game Portal JavaScript** - Update WebSocket handling if needed

## Summary

**Minimum Required Change**: Add the auto-join script to `templates/index.html`

**Optional Changes**:
- Update WebSocket connection logic to use `window.gameWebSocket` if it exists
- Customize UI element selectors if your HTML structure differs
- Ensure game lobby displays correctly after auto-join

The auto-join script is **non-intrusive** - it only activates when `game` and `player_id` URL parameters are present, so it won't affect normal Game Portal usage.

