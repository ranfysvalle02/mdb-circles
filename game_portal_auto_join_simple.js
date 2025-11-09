/**
 * Simple Game Portal Auto-Join Script
 * 
 * Add this to your Game Portal's index.html template or main JavaScript file.
 * It automatically detects game and player_id URL parameters and joins the game.
 */

// Wait for page to load
window.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameId = urlParams.get('game');
    const playerId = urlParams.get('player_id');

    if (!gameId || !playerId) {
        return; // No auto-join needed
    }

    console.log(`Auto-joining game ${gameId} as player ${playerId}`);

    // Hide generic interface elements
    const createForm = document.querySelector('#createGameForm, .create-game-form');
    const joinForm = document.querySelector('#joinGameForm, .join-game-form');
    
    if (createForm) createForm.style.display = 'none';
    if (joinForm) joinForm.style.display = 'none';

    // Show loading state
    showLoading(`Joining game ${gameId}...`);

    // Auto-join the game
    joinGame(gameId, playerId);
});

async function joinGame(gameId, playerId) {
    try {
        const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
        const joinUrl = `${baseUrl}/backend/api/game/${gameId}/join`;

        const response = await fetch(joinUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                player_id: playerId,
                replace_ai: null,
                as_spectator: false
            })
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

        // Connect via WebSocket
        connectWebSocket(gameId, playerId);

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

