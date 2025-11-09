/**
 * Game Portal Auto-Join Script
 * 
 * This script should be added to the Game Portal's index.html or main JavaScript file.
 * It automatically detects game and player_id URL parameters and joins the game.
 */

(function() {
    'use strict';

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutoJoin);
    } else {
        initAutoJoin();
    }

    function initAutoJoin() {
        // Get URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const gameId = urlParams.get('game');
        const playerId = urlParams.get('player_id');

        if (!gameId || !playerId) {
            // No game parameters, show normal interface
            return;
        }

        console.log(`Auto-joining game ${gameId} as player ${playerId}`);

        // Hide the generic interface (create/join forms)
        hideGenericInterface();

        // Show loading state
        showLoadingState(`Joining game ${gameId}...`);

        // Auto-join the game
        autoJoinGame(gameId, playerId);
    }

    function hideGenericInterface() {
        // Hide create game form
        const createForm = document.querySelector('#createGameForm, .create-game-form, [data-create-form]');
        if (createForm) {
            createForm.style.display = 'none';
        }

        // Hide join game form
        const joinForm = document.querySelector('#joinGameForm, .join-game-form, [data-join-form]');
        if (joinForm) {
            joinForm.style.display = 'none';
        }

        // Hide main interface container if it exists
        const mainInterface = document.querySelector('.main-interface, .game-portal-interface');
        if (mainInterface) {
            mainInterface.style.display = 'none';
        }
    }

    function showLoadingState(message) {
        // Create or show loading indicator
        let loadingDiv = document.getElementById('auto-join-loading');
        if (!loadingDiv) {
            loadingDiv = document.createElement('div');
            loadingDiv.id = 'auto-join-loading';
            loadingDiv.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                z-index: 9999;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 2rem;
                border-radius: 8px;
            `;
            document.body.appendChild(loadingDiv);
        }
        loadingDiv.innerHTML = `
            <div style="font-size: 1.2rem; margin-bottom: 1rem;">${message}</div>
            <div class="spinner" style="border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
        `;
        
        // Add spinner animation if not already present
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

    function hideLoadingState() {
        const loadingDiv = document.getElementById('auto-join-loading');
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    async function autoJoinGame(gameId, playerId) {
        try {
            // Get the base URL for API calls
            const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
            
            // Try to join the game via the backend API
            const joinUrl = `${baseUrl}/backend/api/game/${gameId}/join`;
            
            const response = await fetch(joinUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    player_id: playerId,
                    replace_ai: null,
                    as_spectator: false
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }

            const joinResult = await response.json();
            
            console.log('Successfully joined game:', joinResult);

            // Hide loading state
            hideLoadingState();

            // If there's an error in the result, handle it
            if (joinResult.error) {
                if (joinResult.error.includes('already in')) {
                    // Already in game, that's fine - proceed to connect
                    console.log('Already in game, connecting...');
                } else {
                    throw new Error(joinResult.error);
                }
            }

            // Get game info
            const gameInfo = await getGameInfo(gameId);
            
            if (!gameInfo) {
                throw new Error('Could not get game information');
            }

            // Connect to the game (via WebSocket or show game lobby)
            connectToGame(gameId, playerId, gameInfo);

        } catch (error) {
            console.error('Failed to auto-join game:', error);
            hideLoadingState();
            showError(`Failed to join game: ${error.message}`);
        }
    }

    async function getGameInfo(gameId) {
        try {
            const baseUrl = window.location.origin + window.location.pathname.replace(/\/$/, '');
            const gameUrl = `${baseUrl}/backend/api/game/${gameId}`;
            
            const response = await fetch(gameUrl);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Failed to get game info:', error);
            return null;
        }
    }

    function connectToGame(gameId, playerId, gameInfo) {
        // Check if there's a WebSocket connection function
        if (typeof window.connectToGame === 'function') {
            // Use existing WebSocket connection function
            window.connectToGame(gameId, playerId);
            return;
        }

        // Check if there's a function to show the game lobby
        if (typeof window.showGameLobby === 'function') {
            window.showGameLobby(gameId, playerId, gameInfo);
            return;
        }

        // Check if there's a function to initialize the game
        if (typeof window.initGame === 'function') {
            window.initGame(gameId, playerId, gameInfo);
            return;
        }

        // Try to find and trigger the game connection manually
        // This is a fallback - adjust based on your Game Portal's actual structure
        
        // Option 1: Try to find a WebSocket connection button/function
        const wsUrl = `ws://${window.location.host}${window.location.pathname}ws/game/${gameId}/${playerId}`;
        const wsUrlSecure = `wss://${window.location.host}${window.location.pathname}ws/game/${gameId}/${playerId}`;
        
        // Try to establish WebSocket connection
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsPath = window.location.pathname.replace(/\/$/, '') + `/ws/game/${gameId}/${playerId}`;
            const wsUrl = `${protocol}//${window.location.host}${wsPath}`;
            
            console.log('Attempting WebSocket connection to:', wsUrl);
            
            // If there's a global WebSocket manager, use it
            if (window.gameWebSocketManager) {
                window.gameWebSocketManager.connect(gameId, playerId);
                return;
            }

            // Otherwise, create a new WebSocket connection
            const ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                hideLoadingState();
                // The Game Portal should handle the rest via WebSocket messages
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                hideLoadingState();
                showError('Failed to connect to game. Please try refreshing the page.');
            };

            ws.onmessage = (event) => {
                const message = JSON.parse(event.data);
                console.log('WebSocket message:', message);
                
                if (message.type === 'connection_success') {
                    hideLoadingState();
                    // Game is connected, the Game Portal should show the game interface
                }
            };

            // Store WebSocket for later use
            window.gameWebSocket = ws;

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            hideLoadingState();
            showError('Failed to connect to game. Please try manually joining.');
        }
    }

    function showError(message) {
        // Create or show error message
        let errorDiv = document.getElementById('auto-join-error');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.id = 'auto-join-error';
            errorDiv.style.cssText = `
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
            document.body.appendChild(errorDiv);
        }
        errorDiv.innerHTML = `
            <div style="font-size: 1.2rem; margin-bottom: 1rem;">⚠️ Error</div>
            <div style="margin-bottom: 1rem;">${message}</div>
            <button onclick="location.reload()" style="padding: 0.5rem 1rem; background: white; color: #dc3545; border: none; border-radius: 4px; cursor: pointer;">
                Refresh Page
            </button>
        `;
    }

    // Export functions for manual use if needed
    window.autoJoinGame = autoJoinGame;
    window.getGameInfo = getGameInfo;
    window.connectToGame = connectToGame;

})();

