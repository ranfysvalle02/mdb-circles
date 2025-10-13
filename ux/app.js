class YouTubeMiniApp {
    constructor() {
        this.searchEndpoint = 'https://ranfysvalle02--yt-rag-run-ollama-demo.modal.run';
    }

    async search(query = '', channelId = '') {
        if (!query && !channelId) {
            throw new Error('Please provide either a query or a channel ID.');
        }
        const url = `${this.searchEndpoint}?q=${encodeURIComponent(query)}&channel_id=${encodeURIComponent(channelId)}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Search request failed with status ${response.status}.`);
        }
        const data = await response.json();
        // Normalize
        return data.map(item => ({
            id: item.video_id,
            title: item.title,
            imageSrc: item.thumbnail
        }));
    }
}

const ytApp = new YouTubeMiniApp();

// -----------------------------------------------
// Particle configurations (dark mode only):
const particlesConfigDark = {
    particles: {
        number: {
            value: 80,
            density: {
                enable: true,
                value_area: 800
            }
        },
        color: {
            value: ["#00dcff", "#a27bff", "#ffffff"]
        },
        shape: {
            type: "circle"
        },
        opacity: {
            value: {
                min: 0.1,
                max: 0.4
            },
            animation: {
                enable: true,
                speed: 0.8,
                minimumValue: 0.1,
                sync: false
            }
        },
        size: {
            value: {
                min: 1,
                max: 2.5
            }
        },
        line_linked: {
            enable: false
        },
        move: {
            enable: true,
            speed: 0.6,
            direction: "none",
            random: true,
            straight: false,
            out_mode: "out",
            bounce: false
        }
    },
    interactivity: {
        events: {
            onhover: {
                enable: true,
                mode: "repulse"
            },
            onclick: {
                enable: false
            },
            resize: true
        },
        modes: {
            repulse: {
                distance: 100,
                duration: 0.4
            }
        }
    },
    retina_detect: true,
    background: {
        color: "transparent"
    }
};

// -----------------------------------------------
// Theme Initialization (Dark Mode Only):
const initTheme = () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    tsParticles.load('particles-js', particlesConfigDark);
};

// -----------------------------------------------
// Global State & DOM references:
const BASE_URL = 'https://mycircles.oblivio-company.com'; //'http://localhost:8000';
//const BASE_URL = 'http://localhost:8000';
const state = {
    accessToken: localStorage.getItem('accessToken') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    currentUser: null,
    myCircles: [],
    newActivityPostIds: new Set(),
    dashboardFeed: {
        filter: {
            circle_id: null,
            tags: ''
        },
        sortBy: 'newest',
        skip: 0,
        limit: 10,
        hasMore: true,
        posts: [],
        isLoading: false
    },
    circleView: {
        currentCircle: null,
        sortBy: 'newest',
        tags: '',
        skip: 0,
        limit: 10,
        hasMore: true,
        posts: [],
        isLoading: false
    },
    activityCenter: {
        filter: 'all', // 'all', 'invites', 'unread'
        items: [],
        skip: 0,
        limit: 15,
        hasMore: true,
        isLoading: false
    },
    postCreation: {
        type: 'main',
        playlist: {
            videos: []
        },
        linkPreview: {
            data: null,
            url: ''
        },
        imageData: null,
        pollData: {
            question: '',
            options: ['', '']
        },
        wishlist: {
            urls: []
        },
        chat: {
            is_enabled: false,
            participant_ids: []
        }
    },
    postEditing: {
        postId: null,
        circleId: null,
        originalPost: null,
        participant_ids: []
    }
};

const dom = {
    authSection: document.getElementById('authSection'),
    appSection: document.getElementById('appSection'),
    dashboardView: document.getElementById('dashboardView'),
    circleView: document.getElementById('circleView'),
    welcomeMessage: document.getElementById('welcomeMessage'),
    userActions: document.getElementById('userActions'),
    myCirclesContainer: document.getElementById('myCirclesContainer'),
    feedContainer: document.getElementById('feedContainer'),
    circleHeader: document.getElementById('circleHeader'),
    circleFeedContainer: document.getElementById('circleFeedContainer'),
    feedLoader: document.getElementById('feed-loader'),
    circlePostCreatorContainer: null
};

// -----------------------------------------------
// Utilities:
const setButtonLoading = (btn, isLoading) => {
    if (!btn) return;
    btn.disabled = isLoading;
    if (isLoading) {
        btn.dataset.html = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`;
    } else if (btn.dataset.html) {
        btn.innerHTML = btn.dataset.html;
    }
};
const showStatus = (msg, type = 'success') => {
    const id = `a${Date.now()}${Math.random()}`; // A more unique ID
    const container = document.getElementById('globalStatus');

    // This adds the new alert without deleting old ones
    container.insertAdjacentHTML('beforeend', `
      <div id="${id}" class="alert alert-${type} alert-dismissible fade show">
      ${msg}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);

    const alertEl = document.getElementById(id);

    // This makes sure the element is safely removed from the DOM after it fades out
    alertEl.addEventListener('closed.bs.alert', () => {
        alertEl.remove();
    });

    // Automatically start the fade-out animation after 4 seconds
    setTimeout(() => {
        bootstrap.Alert.getOrCreateInstance(alertEl) ?.close();
    }, 4000);
};

/**
 * Extracts the YouTube video ID from a variety of URL formats.
 * @param {string} url The YouTube URL.
 * @returns {string|null} The 11-character video ID or null if not found.
 */
const getYouTubeID = (url) => {
    if (!url) {
        return null;
    }
    // This regex covers:
    // - youtube.com/watch?v=...
    // - youtu.be/...
    // - youtube.com/embed/...
    // - youtube.com/live/...
    // - youtube.com/shorts/...
    // It also correctly ignores extra parameters like timestamps (t=) or playlists (list=).
    const regex = /(?:youtube\.com\/(?:watch\?v=|embed\/|live\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
    const match = url.match(regex);

    return match ? match[1] : null;
};

const linkify = (text) => {
    if (!text) return '';
    // This regex finds URLs and wraps them in an anchor tag.
    const urlRegex = /(\b(https?|ftp|file):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])/ig;
    return text.replace(urlRegex, (url) => {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="embedded-link">${url}</a>`;
    });
};


async function addYoutubeVideoFromUrl(btn) {
    const modal = btn.closest('.modal');
    if (!modal) return;

    // Use different input IDs for create vs edit modals to avoid conflicts
    const inputId = modal.id === 'editPostModal' ? 'editYoutubeUrlInput' : 'youtubeUrlInput';
    const input = document.getElementById(inputId);
    const container = modal.querySelector('.selectedPlaylistVideosContainer');

    if (!input || !container) return;

    const url = input.value.trim();
    if (!url) return;

    const videoId = getYouTubeID(url);
    if (!videoId) {
        return showStatus('Invalid YouTube URL provided.', 'warning');
    }

    // Get the current list of videos directly from the container's data
    const currentVideos = JSON.parse(container.dataset.videos || '[]');
    if (currentVideos.some(v => v.id === videoId)) {
        return showStatus('This video has already been added to the playlist.', 'info');
    }

    setButtonLoading(btn, true);
    try {
        const response = await fetch(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`);
        if (!response.ok) {
            throw new Error('Could not retrieve video details.');
        }
        const data = await response.json();

        const video = {
            id: videoId,
            title: data.title,
            imageSrc: data.thumbnail_url
        };

        const newVideos = [...currentVideos, video];

        renderSelectedPlaylistVideos(container, newVideos);

        // If we are in the "Create Post" modal, we must also update the global state
        if (modal.id === 'createPostModal') {
            state.postCreation.playlist.videos = newVideos;
        }

        input.value = ''; // Clear input on success

    } catch (error) {
        showStatus(error.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}


const debounce = (func, delay) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(null, args), delay);
    };
};

const generateAvatarUrl = (username) => {
    return `https://api.dicebear.com/8.x/rings/svg?seed=${encodeURIComponent(username)}`;
};

// -----------------------------------------------
// API wrapper with token refresh logic:
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
    failedQueue.forEach(prom => {
        if (error) {
            prom.reject(error);
        } else {
            prom.resolve(token);
        }
    });
    failedQueue = [];
};

// ----------------- Smart Activity Polling -----------------

class ActivityPoller {
    constructor(interval = 15000) {
        this.intervalId = null;
        this.pollInterval = interval;
    }

    start() {
        if (this.intervalId) return; // Already running
        console.log("Activity poller starting...");
        this.poll(); // Poll immediately on start
        this.intervalId = setInterval(() => this.poll(), this.pollInterval);
    }

    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log("Activity poller stopped.");
        }
    }

    async poll() {
        if (!state.accessToken) {
            this.stop();
            return;
        }
        try {
            // Fetch only personal invites and notifications for the FAB badge
            const [invites, notifications] = await Promise.all([
                apiFetch('/users/me/invitations'),
                apiFetch('/users/me/notifications?unread_only=true'),
            ]);

            this.updateFab(invites.length, notifications.length);

        } catch (error) {
            console.error("Activity poll failed:", error);
        }
    }

    updateFab(invitesCount, notificationsCount) {
        const totalCount = invitesCount + notificationsCount;
        const fab = document.getElementById('notificationsFab');
        const badge = document.getElementById('notificationsFabBadge');
        if (!fab || !badge) return;

        if (totalCount > 0) {
            badge.textContent = totalCount > 9 ? '9+' : totalCount;
            fab.classList.remove('hidden');
        } else {
            fab.classList.add('hidden');
            badge.textContent = '';
        }
    }
}

const activityPoller = new ActivityPoller();

// ----------------- Notifications & Invites FAB (REFACTORED) -----------------

/**
 * Creates the FAB button and the new single-view modal for the Activity Center.
 * The modal now includes a filter bar instead of tabs.
 */
function createNotificationsFAB() {
    if (document.getElementById('notificationsFab')) return;

    // The FAB button itself remains the same.
    const fabHTML = `
    <div id="notificationsFab" class="notifications-fab hidden" data-bs-toggle="tooltip" title="Activity Center">
        <span id="notificationsFabBadge" class="badge bg-danger rounded-pill"></span>
        <i class="bi bi-bell-fill"></i>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', fabHTML);

    // This is the new, redesigned modal HTML with a single tab and filters.
    const modalHTML = `
    <div class="modal fade" id="notificationsModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Activity Center</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body p-0">
                    <!-- Filter buttons instead of tabs -->
                    <div id="activity-filter-bar" class="p-2 d-flex justify-content-center border-bottom" style="border-color: var(--border-color) !important;">
                        <div class="btn-group btn-group-sm" role="group">
                            <input type="radio" class="btn-check" name="activityFilter" id="filterAll" value="all" autocomplete="off" checked>
                            <label class="btn btn-outline-primary" for="filterAll" data-action="filter-activity" data-filter="all">All</label>

                            <input type="radio" class="btn-check" name="activityFilter" id="filterUnread" value="unread" autocomplete="off">
                            <label class="btn btn-outline-primary" for="filterUnread" data-action="filter-activity" data-filter="unread">Unread</label>

                            <input type="radio" class="btn-check" name="activityFilter" id="filterInvites" value="invites" autocomplete="off">
                            <label class="btn btn-outline-primary" for="filterInvites" data-action="filter-activity" data-filter="invites">Invitations</label>
                        </div>
                    </div>

                    <!-- Single container for all activity items -->
                    <div id="activityListContainer" class="list-group list-group-flush"></div>

                    <!-- Loader for pagination -->
                    <div id="activityLoader" class="text-center p-3 hidden">
                        <span class="spinner-border spinner-border-sm"></span>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-sm btn-outline-primary me-auto" data-action="mark-all-read">Mark all as read</button>
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

function injectFabStyles() {
    const style = document.createElement('style');
    style.textContent = `
    .notifications-fab {
        position: fixed;
        bottom: 20px;
        left: 20px;
        width: 56px;
        height: 56px;
        border-radius: 50%;
        background-color: var(--primary-color);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        cursor: pointer;
        z-index: 1050;
        transition: transform 0.2s ease-in-out, background-color 0.2s;
    }
    .notifications-fab:hover {
        transform: scale(1.1);
        background-color: var(--primary-hover-color);
    }
    .notifications-fab.hidden {
        transform: scale(0);
    }
    .notifications-fab .badge {
        position: absolute;
        top: 0;
        right: 0;
        font-size: 12px;
        line-height: 1;
        padding: 4px 6px;
        transform: translate(25%, -25%);
        pointer-events: none;
    }
    #notificationsModal .modal-content {
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
    }
    #notificationsModal .modal-header,
    #notificationsModal .modal-footer {
        border-bottom: 1px solid var(--border-color);
        border-top: 1px solid var(--border-color);
    }
    #notificationsTab {
        border-bottom: 1px solid var(--border-color);
    }
    #notificationsTab .nav-link {
        color: var(--text-muted);
        border: 0;
        border-bottom: 3px solid transparent;
        transition: all 0.2s ease-in-out;
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    #notificationsTab .nav-link.active {
        color: var(--primary-color);
        background-color: transparent;
        border-bottom-color: var(--primary-color);
        font-weight: 500;
    }
    #notificationsTab .nav-link:hover {
        color: var(--primary-hover-color);
        border-bottom-color: var(--primary-hover-color);
    }
    .invitation-card, .notification-card {
        background-color: transparent !important;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid var(--border-color) !important;
        transition: background-color 0.2s ease;
    }
    .invitation-card:hover, .notification-card:hover {
        background-color: var(--card-bg-hover) !important;
    }
    .list-group-item:last-child {
        border-bottom: 0 !important;
    }
    .notifications-empty-placeholder {
        padding: 3rem 1rem;
        text-align: center;
        color: var(--text-muted);
    }
    .notifications-empty-placeholder i {
        font-size: 2.5rem;
        display: block;
        margin-bottom: 0.5rem;
    }

    /* --- Circle & Post Activity Highlights --- */
    .list-group-item.new-activity-highlight {
        position: relative;
        font-weight: 500;
    }
    .list-group-item.new-activity-highlight > a {
        padding-left: 2rem !important;
    }
    .list-group-item.new-activity-highlight::before {
        content: '';
        position: absolute;
        left: 1rem;
        top: 50%;
        transform: translateY(-50%);
        width: 8px;
        height: 8px;
        background-color: var(--primary-color);
        border-radius: 50%;
        animation: pulse-dot 1.5s infinite ease-in-out;
        z-index: 2;
    }
    @keyframes pulse-dot {
        0% { box-shadow: 0 0 0 0 var(--primary-color-translucent); }
        70% { box-shadow: 0 0 0 6px rgba(0, 123, 255, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 123, 255, 0); }
    }

    .post-card.has-new-activity {
        position: relative;
        border-color: var(--primary-color);
        box-shadow: 0 0 0 1px var(--primary-color);
    }
    .post-card.has-new-activity::after {
        content: 'New Activity';
        position: absolute;
        top: -1px;
        right: -1px;
        background-color: var(--primary-color);
        color: white;
        padding: 3px 10px;
        font-size: 0.7rem;
        font-weight: bold;
        border-top-right-radius: var(--card-border-radius);
        border-bottom-left-radius: var(--card-border-radius);
        animation: bounce-in 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    @keyframes bounce-in {
        0% { transform: scale(0.5); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

      /* --- NEW: Chat Modal Styles --- */
      #chatMessagesContainer {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 1rem;
      min-height: 50vh;
      }
      .chat-bubble-wrapper {
      display: flex;
      max-width: 75%;
      }
      .chat-bubble-wrapper.current-user {
      align-self: flex-end;
      }
      .chat-bubble {
      padding: 0.5rem 0.8rem;
      border-radius: 1rem;
      background-color: var(--card-bg-translucent);
      border: 1px solid var(--border-color);
      }
      .chat-bubble-wrapper.current-user .chat-bubble {
      background-color: var(--primary-color);
      color: white;
      border-color: var(--primary-color);
      }
      .chat-bubble-header {
      font-size: 0.8rem;
      margin-bottom: 0.25rem;
      }
      .chat-bubble-wrapper.current-user .chat-bubble-header {
      display: none;
      }
      .chat-bubble-content {
      margin: 0;
      }
      .chat-bubble-timestamp {
      font-size: 0.7rem;
      opacity: 0.7;
      display: block;
      text-align: right;
      }
    `;
    document.head.appendChild(style);
}

/**
 * Renders the combined list of invites and notifications.
 * This single function replaces both renderInvitationsList and renderNotificationsList.
 */
/**
 * Renders the combined list of all activity items.
 * This function now handles 'invite', 'notification', and 'activity' types.
 */
function renderActivityItems() {
    const container = document.getElementById('activityListContainer');
    const { items, hasMore, skip } = state.activityCenter;

    // If it's the first page and there are no items, show a placeholder.
    if (skip === 0 && items.length === 0) {
        container.innerHTML = `<div class="notifications-empty-placeholder"><i class="bi bi-inbox"></i>All caught up!</div>`;
        return;
    }

    // Use the existing HTML for new items on subsequent loads.
    const itemsToRender = skip > 0 ? items.slice(skip) : items;

    const newItemsHtml = itemsToRender.map(item => {
        // --- INVITATION ---
        if (item.type === 'invite') {
            return `
            <div class="list-group-item invitation-card">
                <div class="d-flex w-100 justify-content-between">
                    <p class="mb-1">
                        <img src="${generateAvatarUrl(item.inviter_username)}" class="avatar-small me-2">
                        <strong>${item.inviter_username}</strong> invited you to join <strong>${item.circle_name}</strong>.
                    </p>
                    <small class="text-nowrap ms-2">${new Date(item.created_at).toLocaleDateString()}</small>
                </div>
                <div class="mt-2 text-end">
                    <button class="btn btn-sm btn-success" data-action="accept-invite" data-invite-id="${item._id}">Accept</button>
                    <button class="btn btn-sm btn-secondary ms-2" data-action="reject-invite" data-invite-id="${item._id}">Decline</button>
                </div>
            </div>`;
        } 
        // --- ACTIVITY EVENT (New) ---
        else if (item.type === 'activity') {
            let contentHtml = '';
            let activityLink = `#/circle/${item.circle_id}`; // Default link to the circle

            if (item.event_type === 'new_post') {
                 contentHtml = `<img src="${generateAvatarUrl(item.actor_username)}" class="avatar-small me-2"> <strong>${item.actor_username}</strong> created a new post.`;
                 // Link could be improved if post details were available
            } else if (item.event_type === 'new_comment') {
                 contentHtml = `<img src="${generateAvatarUrl(item.actor_username)}" class="avatar-small me-2"> <strong>${item.actor_username}</strong> commented on a post.`;
                 if (item.post_id) {
                    activityLink = `javascript:document.querySelector('[data-post-id="${item.post_id}"] [data-action="open-comments"]')?.click()`;
                 }
            } else {
                return ''; // Don't render unknown activity types
            }
            
            return `
            <a href="${activityLink}" onclick="bootstrap.Modal.getInstance('#notificationsModal').hide()" class="list-group-item list-group-item-action notification-card opacity-75">
                <div class="d-flex w-100 justify-content-between align-items-start">
                    <p class="mb-1 small">${contentHtml}</p>
                </div>
                <small class="d-block mt-1">${new Date(item.timestamp).toLocaleString()}</small>
            </a>`;
        }
        // --- NOTIFICATION ---
        else { 
            let contentHtml = '';
            let notificationLink = '#';
            switch (item.type_specific.type) {
                case 'invite_accepted':
                    contentHtml = `<img src="${generateAvatarUrl(item.type_specific.content.invitee_username)}" class="avatar-small me-2"> <strong>${item.type_specific.content.invitee_username}</strong> accepted your invite to <strong>${item.type_specific.content.circle_name}</strong>.`;
                    if (item.type_specific.content.circle_id) {
                        notificationLink = `#/circle/${item.type_specific.content.circle_id}`;
                    }
                    break;
                case 'new_comment':
                    contentHtml = `<img src="${generateAvatarUrl(item.type_specific.content.commenter_username)}" class="avatar-small me-2"> <strong>${item.type_specific.content.commenter_username}</strong> commented on your post in <strong>${item.type_specific.content.circle_name}</strong>.`;
                    if (item.type_specific.content.post_id) {
                        notificationLink = `javascript:document.querySelector('[data-post-id="${item.type_specific.content.post_id}"] [data-action="open-comments"]')?.click()`;
                    }
                    break;
                default:
                    contentHtml = `An unknown notification was received.`;
            }

            const cardContent = `
            <div class="d-flex w-100 justify-content-between align-items-start">
                <p class="mb-1 small">${contentHtml}</p>
                ${!item.is_read ? `<button class="btn btn-sm btn-link p-0 flex-shrink-0 ms-2" data-action="mark-notification-read" data-notification-id="${item._id}" title="Mark as Read"><i class="bi bi-check-circle-fill text-primary"></i></button>` : ''}
            </div>
            <small class="d-block mt-1">${new Date(item.created_at).toLocaleString()}</small>`;

            if (notificationLink !== '#') {
                return `<a href="${notificationLink}" onclick="bootstrap.Modal.getInstance('#notificationsModal').hide()" class="list-group-item list-group-item-action notification-card ${item.is_read ? 'opacity-50' : ''}">${cardContent}</a>`;
            } else {
                return `<div class="list-group-item notification-card ${item.is_read ? 'opacity-50' : ''}">${cardContent}</div>`;
            }
        }
    }).join('');

    container.insertAdjacentHTML('beforeend', newItemsHtml);

    // Add a "Load More" button if there are more items to fetch.
    const loadMoreButton = `<div class="list-group-item text-center"><button class="btn btn-sm btn-primary" data-action="load-more-activity">Load More</button></div>`;
    const existingButton = container.querySelector('[data-action="load-more-activity"]');
    if (existingButton) existingButton.parentElement.remove();
    if (hasMore) container.insertAdjacentHTML('beforeend', loadMoreButton);
}


/**
 * Handles fetching, combining, and paginating all activity types.
 * @param {boolean} isNewFilter - If true, resets items and fetches all data sources.
 */
async function loadActivityItems(isNewFilter = false) {
    const activityState = state.activityCenter;
    if (activityState.isLoading || (!activityState.hasMore && !isNewFilter)) return;

    activityState.isLoading = true;
    const loader = document.getElementById('activityLoader');
    if (loader) loader.classList.remove('hidden');

    const { filter, limit } = activityState;
    
    try {
        if (isNewFilter) {
            activityState.items = [];
            activityState.skip = 0;
            activityState.hasMore = true;
            document.getElementById('activityListContainer').innerHTML = '';

            let combinedItems = [];
            
            // Define API calls based on filter. Activity feed is only fetched on a fresh load.
            const apiPromises = [];
            if (filter === 'all' || filter === 'invites') {
                apiPromises.push(apiFetch('/users/me/invitations'));
            } else {
                apiPromises.push(Promise.resolve([])); // Placeholder for invites
            }
            if (filter === 'all' || filter === 'unread') {
                const unreadOnly = filter === 'unread' ? '&unread_only=true' : '';
                apiPromises.push(apiFetch(`/users/me/notifications?limit=${limit}&skip=0${unreadOnly}`));
                apiPromises.push(apiFetch('/users/me/activity-feed'));
            } else {
                apiPromises.push(Promise.resolve([])); // Placeholder for notifications
                apiPromises.push(Promise.resolve([])); // Placeholder for activity
            }

            const [invites, notifications, activityEvents] = await Promise.all(apiPromises);

            // Normalize and combine all data sources
            const normalizedInvites = invites.map(invite => ({ ...invite, type: 'invite', timestamp: invite.created_at }));
            const normalizedNotifications = notifications.map(notif => ({ ...notif, type: 'notification', type_specific: notif, timestamp: notif.created_at }));
            const normalizedActivity = activityEvents.map(event => ({ ...event, type: 'activity' })); // `timestamp` already exists

            combinedItems = [...normalizedInvites, ...normalizedNotifications, ...normalizedActivity];
            combinedItems.sort((a, b) => new Date(b.timestamp || b.created_at) - new Date(a.timestamp || a.created_at));

            activityState.items = combinedItems;
            activityState.hasMore = notifications.length === limit; // Pagination is driven by notifications
        } else {
            // "Load More" only paginates notifications
            activityState.skip = activityState.items.length;
            const newNotifications = await apiFetch(`/users/me/notifications?limit=${limit}&skip=${activityState.skip}`);
            
            const normalizedNew = newNotifications.map(notif => ({ ...notif, type: 'notification', type_specific: notif, timestamp: notif.created_at }));
            activityState.items.push(...normalizedNew);
            activityState.hasMore = newNotifications.length === limit;
        }

        renderActivityItems();

    } catch (error) {
        document.getElementById('activityListContainer').innerHTML = `<div class="p-4 text-center text-danger">Could not load activity.</div>`;
    } finally {
        activityState.isLoading = false;
        if (loader) loader.classList.add('hidden');
    }
}

/**
 * Handles the logic for fetching, combining, and paginating all activity items.
 * @param {boolean} isNewFilter - If true, resets the items and pagination.
 */
async function loadActivityItems(isNewFilter = false) {
    const activityState = state.activityCenter;
    if (activityState.isLoading || (!activityState.hasMore && !isNewFilter)) return;

    activityState.isLoading = true;
    const loader = document.getElementById('activityLoader');
    if (loader) loader.classList.remove('hidden');

    if (isNewFilter) {
        activityState.items = [];
        activityState.skip = 0;
        activityState.hasMore = true;
        document.getElementById('activityListContainer').innerHTML = '';
    }

    // Define API calls based on the current filter
    const {
        filter,
        limit,
        skip
    } = activityState;
    const apiCalls = [];
    if (filter === 'all' || filter === 'unread' || filter === 'invites') {
        // Invites are always considered "unread"
        apiCalls.push(apiFetch('/users/me/invitations'));
    }
    if (filter === 'all' || filter === 'unread') {
        const unreadOnly = filter === 'unread' ? '&unread_only=true' : '';
        apiCalls.push(apiFetch(`/users/me/notifications?limit=${limit}&skip=${skip}${unreadOnly}`));
    }

    try {
        const results = await Promise.all(apiCalls);
        let combinedItems = [];

        // Normalize invites
        const invites = results[0].map(invite => ({ ...invite,
            type: 'invite',
            is_read: false
        }));

        // Normalize notifications
        let notifications = [];
        if (filter !== 'invites') {
            notifications = (results[1] || []).map(notif => ({
                _id: notif._id,
                created_at: notif.created_at,
                is_read: notif.is_read,
                type: 'notification',
                type_specific: notif, // Keep original notification data nested
            }));
            // Update hasMore based on notification results, as they are the paginated source
            activityState.hasMore = notifications.length === limit;
        } else {
            activityState.hasMore = false; // No pagination for invites-only view
        }

        // Combine, sort, and update state
        if (isNewFilter) {
            combinedItems = [...invites, ...notifications];
        } else {
            // When loading more, we only add new notifications
            combinedItems = [...activityState.items, ...notifications];
        }

        combinedItems.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

        activityState.skip = activityState.items.length; // Record where the new items start
        activityState.items = combinedItems;

        renderActivityItems();

    } catch (error) {
        document.getElementById('activityListContainer').innerHTML = `<div class="p-4 text-center text-danger">Could not load activity.</div>`;
    } finally {
        activityState.isLoading = false;
        if (loader) loader.classList.add('hidden');
    }
}

/**
 * Opens the modal and triggers the initial data load for the activity center.
 */
async function openNotificationsModal() {
    const modal = bootstrap.Modal.getOrCreateInstance('#notificationsModal');
    modal.show();
    // Set the radio button to match the current filter in the state
    document.getElementById(`filter${state.activityCenter.filter.charAt(0).toUpperCase() + state.activityCenter.filter.slice(1)}`).checked = true;
    // Trigger a fresh load of data
    await loadActivityItems(true);
}


async function apiFetch(endpoint, options = {}) {
    const customOptions = {
        ...options,
        headers: {
            ...options.headers,
            'Content-Type': 'application/json'
        }
    };
    if (state.accessToken) {
        customOptions.headers['Authorization'] = `Bearer ${state.accessToken}`;
    }

    let response = await fetch(`${BASE_URL}${endpoint}`, customOptions);

    if (response.status === 401 && state.refreshToken) {
        if (isRefreshing) {
            return new Promise((resolve, reject) => {
                failedQueue.push({
                    resolve,
                    reject
                });
            }).then(() => {
                customOptions.headers['Authorization'] = `Bearer ${state.accessToken}`;
                return fetch(`${BASE_URL}${endpoint}`, customOptions);
            });
        }
        isRefreshing = true;
        try {
            const refreshResponse = await fetch(`${BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    refresh_token: state.refreshToken
                })
            });
            if (!refreshResponse.ok) throw new Error("Refresh failed");
            const tokenData = await refreshResponse.json();
            storeTokens(tokenData.access_token, tokenData.refresh_token);
            processQueue(null, tokenData.access_token);
            customOptions.headers['Authorization'] = `Bearer ${state.accessToken}`;
            response = await fetch(`${BASE_URL}${endpoint}`, customOptions);
        } catch (err) {
            processQueue(err, null);
            logout();
            return Promise.reject(err);
        } finally {
            isRefreshing = false;
        }
    }

    if (!response.ok) {
        let errData = {};
        try {
            errData = await response.json();
        } catch {}
        const detail = errData.detail || `Error: ${response.status}`;
        const err = new Error(detail);
        err.status = response.status;
        if (response.status !== 403 && response.status !== 401) {
            showStatus(detail, 'danger');
        }
        throw err;
    }
    return response.status === 204 ? null : response.json();
}

const storeTokens = (access, refresh) => {
    state.accessToken = access;
    state.refreshToken = refresh;
    localStorage.setItem('accessToken', access);
    localStorage.setItem('refreshToken', refresh);
};

const logout = () => {
    activityPoller.stop();
    state.accessToken = null;
    state.refreshToken = null;
    state.currentUser = null;
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('pendingInviteToken');
    document.getElementById('notificationsFab') ?.classList.add('hidden');
    window.location.hash = '';
    handleRoute();
};

// -----------------------------------------------
// Auth:
const login = async (username, password) => {
    const data = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({
            username,
            password
        })
    });
    storeTokens(data.access_token, data.refresh_token);
    await handleRoute();
    showStatus('Login successful!', 'success');
    return true;
};

const register = async (username, password) => {
    await apiFetch('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
            username,
            password
        })
    });
    showStatus('Registration successful! Please log in.', 'success');
    return true;
};

async function fetchAndRenderAll() {
    await fetchCurrentUser();
    await renderAllSidebarComponents();
}

async function fetchCurrentUser() {
    if (!state.accessToken) return;
    try {
        state.currentUser = await apiFetch('/users/me');
    } catch (error) {
        console.error("Token might be invalid, logging out.", error);
        logout();
    }
}

// -----------------------------------------------
// Routing / Views:
async function handleRoute() {
    await fetchCurrentUser();

    if (state.currentUser) {
        await renderAllSidebarComponents();
        activityPoller.start();
    } else {
        activityPoller.stop();
    }

    const hash = window.location.hash;
    const circleRouteMatch = hash.match(/^#\/circle\/(.+)$/);
    const joinCircleMatch = hash.match(/^#\/join-circle\/(.+)$/);

    const pendingInviteToken = localStorage.getItem('pendingInviteToken');
    if (pendingInviteToken && state.currentUser) {
        localStorage.removeItem('pendingInviteToken');
        await handleJoinByToken(pendingInviteToken, true);
        return;
    }

    if (joinCircleMatch) {
        await handleJoinByToken(joinCircleMatch[1]);
    } else if (circleRouteMatch) {
        state.dashboardFeed.filter.circle_id = null;
        await showCircleView(circleRouteMatch[1]);
    } else {
        await showDashboardView();
    }
}

async function showDashboardView() {
    dom.circleView.classList.add('hidden');
    if (state.currentUser) {
        dom.authSection.classList.add('hidden');
        dom.appSection.classList.remove('hidden');
        dom.dashboardView.classList.remove('hidden');
        dom.welcomeMessage.innerHTML = `Welcome, ${state.currentUser.username}! <img src="${generateAvatarUrl(state.currentUser.username)}" class="avatar avatar-sm ms-2">`;
        dom.userActions.classList.remove('hidden');
        await renderDashboard();
    } else {
        dom.appSection.classList.add('hidden');
        dom.authSection.classList.remove('hidden');
    }
}

async function showCircleView(circleId) {
    // When a user views a circle, find the parent item and remove its activity highlight
    const circleLink = document.querySelector(`#myCirclesContainer a[data-circle-id="${circleId}"]`);
    if (circleLink) {
        const listItem = circleLink.closest('.list-group-item');
        if (listItem) {
            listItem.classList.remove('new-activity-highlight');
        }
    }

    state.circleView.currentCircle = null;
    dom.authSection.classList.add('hidden');
    dom.dashboardView.classList.add('hidden');
    dom.appSection.classList.remove('hidden');
    dom.circleView.classList.remove('hidden');
    dom.welcomeMessage.textContent = `Viewing a Circle`;
    dom.userActions.classList.toggle('hidden', !state.currentUser);
    await resetAndRenderCircleFeed(circleId);
}

async function renderDashboard() {
    renderMyCircles(state.myCircles);
    try {
        await resetAndRenderDashboardFeed();
    } catch (error) {
        console.error("Failed to load dashboard data", error);
    }
}

async function renderAllSidebarComponents() {
    if (!state.currentUser) return;
    try {
        const myCircles = await apiFetch('/circles/mine');
        state.myCircles = myCircles;
        renderMyCircles(myCircles);
    } catch (error) {
        console.error("Failed to load sidebar components", error);
        dom.myCirclesContainer.innerHTML = `<div class="empty-placeholder text-danger small">Could not load circles.</div>`;
    }
}

function renderMyCircles(circles) {
    const {
        circle_id
    } = state.dashboardFeed.filter;
    const createCircleBtn = document.getElementById('createCircleBtn');

    let html = `
    <a href="#"
    class="list-group-item clickable list-group-item-action ${!circle_id ? 'active' : ''}"
    data-action="filter-feed" data-circle-id="">
    <i class="bi bi-collection-fill me-2"></i>All My Circles
    </a>
    `;

    if (circles.length === 0) {
        html += `
        <div class="text-center p-3 mt-2">
        <h5 class="mb-2"> Welcome to myCircles!</h5>
        <p class=" small">It looks like you're not in any circles yet.</p>
        <p class=" small">Get started by creating your own private space. Just click the <strong class="text-success"><i class="bi bi-plus-circle"></i> New Circle</strong> button above!</p>
        </div>
        `;
        createCircleBtn.classList.add('highlight-wiggle');
    } else {
        html += circles.map(c => `
        <div class="list-group-item d-flex justify-content-between align-items-center p-0">
        <a href="#/circle/${c._id}"
        class="flex-grow-1 list-group-item-action border-0 clickable px-3 py-2"
        data-circle-id="${c._id}" data-bs-toggle="tooltip" title="${c.name}">
        <i class="bi bi-hash"></i> ${c.name}
        </a>
        </div>
        `).join('');
        createCircleBtn.classList.remove('highlight-wiggle');
    }

    dom.myCirclesContainer.innerHTML = html;
    initTooltips();
}

async function resetAndRenderDashboardFeed() {
    state.dashboardFeed.skip = 0;
    state.dashboardFeed.hasMore = true;
    state.dashboardFeed.posts = [];
    dom.feedContainer.innerHTML = '';
    await renderDashboardFeed();
}

async function renderDashboardFeed() {
    if (!state.dashboardFeed.hasMore || state.dashboardFeed.isLoading) return;
    state.dashboardFeed.isLoading = true;
    dom.feedLoader.classList.remove('hidden');

    const {
        filter,
        skip,
        limit,
        sortBy
    } = state.dashboardFeed;
    let url = `/feed?skip=${skip}&limit=${limit}&sort_by=${sortBy}`;
    if (filter.circle_id) url += `&circle_id=${filter.circle_id}`;
    if (filter.tags) url += `&tags=${encodeURIComponent(filter.tags)}`;

    try {
        const feedData = await apiFetch(url);
        state.dashboardFeed.posts.push(...feedData.posts);
        appendPosts(feedData.posts, dom.feedContainer);
        state.dashboardFeed.hasMore = feedData.has_more;
        state.dashboardFeed.skip += feedData.posts.length;

        if (dom.feedContainer.innerHTML === '' && !feedData.has_more) {
            dom.feedContainer.innerHTML = `<div class="empty-placeholder">Your feed is empty. Post something or broaden your filters!</div>`;
        }
    } catch (error) {
        dom.feedContainer.innerHTML = `<div class="empty-placeholder text-danger">Could not load feed.</div>`;
    } finally {
        state.dashboardFeed.isLoading = false;
        dom.feedLoader.classList.add('hidden');
    }
}

// -----------------------------------------------
// Circle View & Feed:
async function resetAndRenderCircleFeed(circleId) {
    state.circleView.skip = 0;
    state.circleView.hasMore = true;
    state.circleView.posts = [];
    dom.circleFeedContainer.innerHTML = '';
    dom.circleHeader.innerHTML = '';
    await renderCircleFeed(circleId);
}

async function renderCircleFeed(circleId) {
    const feedState = state.circleView;
    if (!feedState.hasMore || feedState.isLoading) return;

    feedState.isLoading = true;
    dom.feedLoader.classList.remove('hidden');

    try {
        // --- Step 1: Fetch Circle Header Details ---
        if (feedState.skip === 0) {
            const circleDetails = await apiFetch(`/circles/${circleId}`);
            feedState.currentCircle = circleDetails;

            const userRole = circleDetails.user_role;
            const canManage = state.currentUser && (userRole === 'admin' || userRole === 'moderator');
            const managementControlsHtml = canManage ? `
           <button class="btn btn-sm btn-secondary"
              data-action="open-manage-circle" data-circle-id="${circleDetails._id}">
           <i class="bi bi-gear-fill"></i> Manage
           </button>` : '';

            dom.circleHeader.innerHTML = `
           <div class="d-flex justify-content-between align-items-center flex-wrap gap-3">
           <div>
              <h2>
              <i class="bi bi-hash"></i> ${circleDetails.name}
              ${circleDetails.is_public ? '<span class="badge bg-info ms-2" title="This circle is public">Public</span>' : ''}
              </h2>
              <p class="mb-0">${circleDetails.description || 'A shared space for posts.'}</p>
           </div>
           <div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">
              <a href="#" class="btn btn-secondary btn-sm"><i class="bi bi-arrow-left"></i> Back to Dashboard</a>
              <div class="input-group input-group-sm" style="width: auto;">
              <span class="input-group-text bg-transparent border-end-0" style="border-color: var(--border-color);"><i class="bi bi-tags"></i></span>
              <input type="text" id="circleTagFilter" class="form-control border-start-0" placeholder="Filter by tags..." value="${feedState.tags}" style="min-width: 150px;">
              </div>
              ${state.currentUser ? `
              <div class="btn-group">
                 <button class="btn btn-sm btn-success" data-action="invite-to-circle" data-circle-id="${circleId}">
                 <i class="bi bi-send"></i> Invite
                 </button>
                 ${managementControlsHtml}
              </div>
              <button id="togglePostCreatorCircleBtn" class="btn btn-sm btn-primary ms-2">
                 <i class="bi bi-pencil-square"></i> New Post
              </button>
              ` : ''}
           </div>
           </div>`;
        }

        // --- Step 2: Fetch Circle Feed (Posts) ---
        let url = `/circles/${circleId}/feed?skip=${feedState.skip}&limit=${feedState.limit}&sort_by=${feedState.sortBy}`;
        if (feedState.tags) {
            url += `&tags=${encodeURIComponent(feedState.tags)}`;
        }
        const feedData = await apiFetch(url);

        state.circleView.posts.push(...feedData.posts);
        appendPosts(feedData.posts, dom.circleFeedContainer, feedState.currentCircle.name);
        feedState.hasMore = feedData.has_more;
        feedState.skip += feedData.posts.length;

        if (!dom.circleFeedContainer.querySelector('.post-card-wrapper') && !feedData.has_more) {
            dom.circleFeedContainer.insertAdjacentHTML('beforeend', `<div class="empty-placeholder">This circle has no posts yet.</div>`);
        }

    } catch (error) {
        // --- Step 3: Improved Error Handling ---
        dom.circleHeader.innerHTML = ''; // Clear the header on error
        let errorMessage = `<div class="empty-placeholder text-danger">Could not load this circle. It may not exist or is private.</div>`;
        if (error.status === 401) {
            errorMessage = `<div class="empty-placeholder">This is a private circle. Please <a href="#" onclick="window.location.hash=''; handleRoute(); return false;">log in</a> to view.</div>`;
        } else if (error.status === 403) {
            errorMessage = `<div class="empty-placeholder">You are not a member of this private circle. Please request an invite.</div>`;
        }
        dom.circleFeedContainer.innerHTML = errorMessage;
    } finally {
        feedState.isLoading = false;
        dom.feedLoader.classList.add('hidden');
    }
}

// -----------------------------------------------
// Post loading / "seen" tracking:
const postObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const postWrapper = entry.target;
            const postId = postWrapper.dataset.postId;
            if (postId && postWrapper.dataset.seenSent !== 'true') {
                postWrapper.dataset.seenSent = 'true';
                markPostAsSeen(postId);
                observer.unobserve(postWrapper);
            }
        }
    });
}, {
    threshold: 0.75
});

async function markPostAsSeen(postId) {
    if (!state.currentUser) return;
    try {
        await apiFetch(`/posts/${postId}/seen`, {
            method: 'POST'
        });
        const postWrapper = document.querySelector(`.post-card-wrapper[data-post-id="${postId}"]`);
        if (postWrapper && !postWrapper.querySelector('.seen-by-container.seen-by-user')) {
            const seenContainer = postWrapper.querySelector('.seen-by-container');
            const count = parseInt(seenContainer.dataset.seenCount || '0', 10);
            const newCount = count + 1;
            seenContainer.dataset.seenCount = newCount;
            seenContainer.classList.add('seen-by-user');
            const avatarStack = seenContainer.querySelector('.avatar-stack');
            const textEl = seenContainer.querySelector('.seen-by-text');
            const userAvatar = document.createElement('img');
            userAvatar.src = generateAvatarUrl(state.currentUser.username);
            userAvatar.className = 'avatar-small';
            userAvatar.title = state.currentUser.username;
            avatarStack.prepend(userAvatar);
            textEl.textContent = `${newCount} view${newCount > 1 ? 's' : ''}`;
        }
    } catch (error) {
        console.error(`Failed to mark post ${postId} as seen.`, error);
        const postWrapper = document.querySelector(`.post-card-wrapper[data-post-id="${postId}"]`);
        if (postWrapper) postWrapper.dataset.seenSent = 'false';
    }
}

function appendPosts(posts, container, circleName = null) {
    const postsHtml = posts
        .filter(post => post && (post.id || post._id))
        .map(post => {
            let contentHtml = '';
            const postType = post.content.post_type || 'standard';
            const postId = post.id || post._id;
            const hasNewActivity = state.newActivityPostIds.has(postId);

            switch (postType) {
                case 'yt-playlist':
                    {
                        const playlist = post.content.playlist_data;
                        const coverImage = playlist.videos.length > 0 ?
                            playlist.videos[0].imageSrc :
                            'https://via.placeholder.com/400x225.png?text=Playlist';
                        const playlistDataString = JSON.stringify(playlist)
                            .replace(/'/g, "'")
                            .replace(/"/g, '"');
                        contentHtml = `
<div class="card mt-3 playlist-card"
style="background-color: var(--form-input-bg); border-color: var(--border-color); position: relative;">
<img src="${coverImage}" class="card-img-top" alt="Playlist Cover">
<div class="card-body">
<h5 class="card-title mb-1">${playlist.name}</h5>
<p class="card-text small">${playlist.videos.length} videos</p>
</div>
<div class="playlist-play-overlay"
data-action="play-playlist"
data-playlist='${playlistDataString}'>
<i class="bi bi-play-circle-fill"></i><span>Play All</span>
</div>
</div>
`;
                        break;
                    }
                case 'poll':
                    {
                        const poll = post.content.poll_data;
                        const results = post.poll_results;
                        const isPollActive = results && !results.is_expired;
                        const totalVotes = results ? results.total_votes : 0;
                        const userVotedIndex = results ? results.user_voted_index : -1;

                        const pollOptionsHtml = results.options.map((option, index) => {
                            const percentage = totalVotes > 0 ? (option.votes / totalVotes) * 100 : 0;
                            const isVotedByUser = userVotedIndex === index;
                            const voteAction = isPollActive ?
                                `data-action="vote-poll" data-post-id="${postId}" data-option-index="${index}"` :
                                '';
                            return `
<div class="poll-option ${isVotedByUser ? 'voted-by-user' : ''} ${!isPollActive ? 'poll-disabled' : ''}"
${voteAction}>
<div class="progress" style="width: ${percentage}%;"></div>
<div class="d-flex justify-content-between align-items-center position-relative">
<span>${option.text} ${isVotedByUser ? '<i class="bi bi-check-circle-fill"></i>' : ''}</span>
<span class="fw-bold small">${percentage.toFixed(0)}% (${option.votes})</span>
</div>
</div>
`;
                        }).join('');

                        let pollFooterHtml = '';
                        if (results && results.expires_at) {
                            const expiresDate = new Date(results.expires_at);
                            if (isPollActive) {
                                const now = new Date();
                                const diffMs = expiresDate - now;
                                const diffHours = Math.floor(diffMs / 3600000);
                                const diffMins = Math.round((diffMs % 3600000) / 60000);
                                let timeRemaining = 'Closing soon';
                                if (diffHours > 24) {
                                    timeRemaining = `${Math.floor(diffHours / 24)}d left`;
                                } else if (diffHours > 0) {
                                    timeRemaining = `${diffHours}h left`;
                                } else if (diffMins > 0) {
                                    timeRemaining = `${diffMins}m left`;
                                }
                                pollFooterHtml = `
<small class="">
Total votes: ${totalVotes} <i class="bi bi-clock"></i> ${timeRemaining}
</small>
`;
                            } else {
                                pollFooterHtml = `
<small class="">
<strong><i class="bi bi-lock-fill"></i> Poll closed on ${expiresDate.toLocaleDateString()}</strong>
${totalVotes} votes
</small>
`;
                            }
                        } else {
                            pollFooterHtml = `<small class="">Total votes: ${totalVotes}</small>`;
                        }

                        contentHtml = `
<h5 class="card-title">${poll.question}</h5>
<div class="poll-container">${pollOptionsHtml}</div>
${pollFooterHtml}
`;
                        break;
                    }
                case 'wishlist':
                    {
                        const rawWishlistData = post.content.wishlist_data;
                        const wishlistItems = Array.isArray(rawWishlistData) ? rawWishlistData : [];

                        if (post.content.text) {
                            contentHtml += `<p class="card-text" style="white-space: pre-wrap;">${post.content.text}</p>`;
                        }

                        let itemsHtml = '<div class="list-group list-group-flush mt-3">';

                        wishlistItems.forEach(item => {
                            if (!item || !item.url) return;

                            let imageHtml = '';

                            if (item.image && !item.image.includes('transparent-pixel')) {
                                imageHtml = `<img src="${item.image}" class="wishlist-item-image me-3" alt="${item.title || 'Wishlist item'}">`;
                            } else {
                                try {
                                    const domain = new URL(item.url).hostname;
                                    imageHtml = `<img src="https://www.google.com/s2/favicons?domain=${domain}&sz=32" class="favicon me-2" alt="${domain} favicon">`;
                                } catch (e) {
                                    imageHtml = `<i class="bi bi-link-45deg me-2"></i>`;
                                }
                            }

                            itemsHtml += `
<a href="${item.url}" target="_blank" rel="noopener noreferrer"
class="list-group-item list-group-item-action d-flex align-items-center">
${imageHtml}
<div class="wishlist-item-details">
<strong class="d-block text-truncate">${item.title || item.url}</strong>
<small class="text-truncate">${item.description || new URL(item.url).hostname.replace('www.','')}</small>
</div>
<i class="bi bi-box-arrow-up-right ms-auto"></i>
</a>
`;
                        });

                        itemsHtml += '</div>';
                        contentHtml += itemsHtml;

                        break;
                    }
                case 'image':
                    {
                        const img = post.content.image_data;
                        if (img && img.url) {
                            const captionHtml = img.caption ?
                                `<div class="card-body"><p class="card-text" style="white-space: pre-wrap;color:white;">${img.caption}</p></div>` :
                                '';

                            contentHtml = `
<div class="card mt-3" style="background-color: var(--form-input-bg); border-color: var(--border-color);">
<img src="${img.url}" class="card-img-top" alt="User's posted image">
${captionHtml}
</div>
`;
                        } else {
                            contentHtml = `<p class="">No image data found.</p>`;
                        }
                        break;
                    }
                case 'spotify_playlist':
                    {
                        const spotifyData = post.content.spotify_playlist_data;
                        if (spotifyData && spotifyData.embed_url) {
                            if (post.content.text) { // Allow optional text above the embed
                                contentHtml += `<p class="card-text" style="white-space: pre-wrap;">${post.content.text}</p>`;
                            }
                            contentHtml += `
<div class="mt-3">
<iframe
style="border-radius:12px"
src="${spotifyData.embed_url}"
width="100%"
height="352"
frameBorder="0"
allowfullscreen=""
allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
loading="lazy">
</iframe>
</div>
`;
                        } else {
                            contentHtml = `<p class="">Could not load Spotify playlist.</p>`;
                        }
                        break;
                    }
                default:
                    {
                        if (post.content.text) {
                            contentHtml += `<p class="card-text" style="white-space: pre-wrap;">${linkify(post.content.text)}</p>`;
                        }
                        if (post.content.link) {
                            const videoId = getYouTubeID(post.content.link);
                            if (videoId) {
                                contentHtml += `
<div class="video-container my-2">
<iframe
src="https://www.youtube.com/embed/${videoId}"
title="YouTube video player" frameborder="0"
allow="accelerometer; autoplay; clipboard-write; encrypted-media;
gyroscope; picture-in-picture" allowfullscreen>
</iframe>
</div>
`;
                            } else {
                                try {
                                    const host = new URL(post.content.link).hostname;
                                    contentHtml += `
<a href="${post.content.link}" target="_blank" rel="noopener noreferrer"
class="link-preview d-block text-decoration-none">
<strong class="link-preview-title d-block">${post.content.link}</strong>
<span class="link-preview-host">${host}</span>
</a>
`;
                                } catch (e) {
                                    contentHtml += `<p class="">Invalid link: ${post.content.link}</p>`;
                                }
                            }
                        }
                        break;
                    }
            }

            if (post.content.tags && post.content.tags.length > 0) {
                contentHtml += `
<div class="mt-3 post-tags">
${post.content.tags.map(tag => `
<span class="badge rounded-pill bg-secondary me-1"
data-action="filter-by-tag" data-tag="${tag}">
${tag}
</span>
`).join(' ')}
</div>
`;
            }

            const seenByUsers = post.seen_by_user_objects || [];
            const seenCount = post.seen_by_count;
            let seenByText;
            if (seenCount === 0) {
                seenByText = 'Be the first to see this!';
            } else if (seenCount === 1) {
                seenByText = `Seen by ${seenByUsers[0]?.username || '1 person'}`;
            } else if (seenCount === 2 && seenByUsers.length === 2) {
                seenByText = `Seen by ${seenByUsers[0].username} and ${seenByUsers[1].username}`;
            } else {
                seenByText = `Seen by ${seenByUsers[0]?.username || ''} and ${seenCount - 1} others`;
            }

            const chatButtonHtml = (post.is_chat_enabled && post.chat_participants) ? `
<button class="btn btn-sm btn-link text-decoration-none p-0 post-action-btn"
style="color: var(--text-color);"
data-action="open-chat"
data-post-id="${postId}"
data-post-author-id="${post.author_id}"
title="Open Group Chat">
<i class="bi bi-chat-dots-fill"></i> Chat
</button>
` : '';

            const postFooter = `
<div class="post-footer mt-3 pt-3 d-flex justify-content-between align-items-center">
<div class="seen-by-container ${post.is_seen_by_user ? 'seen-by-user' : ''}"
data-action="show-seen-status" data-post-id="${postId}"
data-seen-count="${seenCount}"
title="See who has viewed this post">
<div class="avatar-stack">
${seenByUsers.map(user => `
<img src="${generateAvatarUrl(user.username)}"
class="avatar-small"
title="${user.username}">
`).join('')}
</div>
<span class="seen-by-text">${seenByText}</span>
</div>
<div class="post-actions d-flex align-items-center gap-3">
${chatButtonHtml}
<button class="btn btn-sm btn-link text-decoration-none p-0
post-action-btn"
style="color: var(--text-color);"
data-action="open-comments"
data-post-id="${postId}"
data-post-author-username="${post.author_username}"
title="Open Comments">
<i class="bi bi-chat-left-text"></i> ${post.comment_count || 0}
</button>
</div>
</div>
`;

            const displayCircleName = circleName || post.circle_name;
            const canModify = state.currentUser && post.author_username === state.currentUser.username;
            const dropdownMenu = canModify ? `
<div class="dropdown">
<button class="btn btn-sm py-0 px-2" type="button"
data-bs-toggle="dropdown"
data-bs-toggle="tooltip"
title="More options">
<i class="bi bi-three-dots-vertical"></i>
</button>
<ul class="dropdown-menu dropdown-menu-dark">
<li>
<a class="dropdown-item" href="#"
data-action="open-edit-post"
data-post-id="${postId}"
data-circle-id="${post.circle_id}">
<i class="bi bi-pencil-fill me-2"></i>Edit Post
</a>
</li>
<li>
<a class="dropdown-item text-danger" href="#"
data-action="delete-post"
data-post-id="${postId}"
data-circle-id="${post.circle_id}">
<i class="bi bi-trash-fill me-2"></i>Delete Post
</a>
</li>
</ul>
</div>
` : '';

            return `
<div class="post-card-wrapper"
data-post-id="${postId}"
data-post-wrapper-id="${postId}">
<div class="glass-card post-card ${hasNewActivity ? 'has-new-activity' : ''}" data-post-id="${postId}">
<div class="post-card-body">
<div class="d-flex justify-content-between align-items-start">
<div class="d-flex align-items-center">
<img src="${generateAvatarUrl(post.author_username)}" class="avatar me-3">
<div>
<strong class="d-block">${post.author_username}</strong>
<small>
in <a href="#/circle/${post.circle_id}"
class="text-reset fw-bold">
${displayCircleName}
</a> ${new Date(post.created_at).toLocaleString()}
</small>
</div>
</div>
${dropdownMenu}
</div>
<div class="mt-3">${contentHtml}</div>
${postFooter}
</div>
</div>
</div>
`;
        }).join('');

    container.insertAdjacentHTML('beforeend', postsHtml);

    const newPostElements = container.querySelectorAll(`.post-card-wrapper:not([data-observed="true"])`);
    newPostElements.forEach(el => {
        el.dataset.observed = "true";
        postObserver.observe(el);
    });
    initTooltips();
}

const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
        if (!dom.circleView.classList.contains('hidden') && state.circleView.currentCircle) {
            renderCircleFeed(state.circleView.currentCircle._id);
        } else if (!dom.dashboardView.classList.contains('hidden')) {
            renderDashboardFeed();
        }
    }
}, {
    rootMargin: '200px'
});
observer.observe(dom.feedLoader);

// -----------------------------------------------
// Auth transitions (unchanged):
const switchAuthView = (hideEl, showEl) => {
    hideEl.classList.add('animate-out');
    hideEl.addEventListener('animationend', () => {
        hideEl.classList.add('hidden');
        hideEl.classList.remove('animate-out');
        showEl.classList.remove('hidden');
        showEl.classList.add('animate-in');
        showEl.addEventListener('animationend', () => {
            showEl.classList.remove('animate-in');
            if (showEl.id === 'authFormContainer') {
                document.getElementById('usernameInput').focus();
            }
        }, {
            once: true
        });
    }, {
        once: true
    });
};

async function handleAuthAction(e, action) {
    const btn = e.currentTarget;
    const u = document.getElementById('usernameInput').value;
    const p = document.getElementById('passwordInput').value;
    if (!u || !p) return showStatus('Username and password are required', 'warning');

    setButtonLoading(btn, true);
    try {
        await action(u, p);
    } catch (error) {
        // Error is shown by apiFetch or showStatus
    } finally {
        setButtonLoading(btn, false);
    }
}

// -----------------------------------------------
// Creating or joining circles:
async function handleCreateCircle() {
    const btn = document.getElementById('submitCircleButton');
    const name = document.getElementById('circleName').value;
    const description = document.getElementById('circleDescription').value;

    if (!name.trim()) {
        return showStatus('Circle name cannot be empty', 'warning');
    }

    const payload = {
        name,
        description
    };

    setButtonLoading(btn, true);
    try {
        const newCircle = await apiFetch('/circles', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        showStatus(`Circle "${newCircle.name}" created! Navigating...`, 'success');
        bootstrap.Modal.getInstance('#createCircleModal').hide();
        document.getElementById('createCircleForm').reset();

        await renderAllSidebarComponents();

        window.location.hash = `#/circle/${newCircle._id}`;
    } catch (error) {
        // Error is shown by apiFetch
    } finally {
        setButtonLoading(btn, false);
    }
}

// -----------------------------------------------
// Post creation logic:
async function handleImageUpload(file) {
    const previewContainer = document.getElementById('imageUploadPreviewContainer');
    const previewImg = document.getElementById('imageUploadPreview');
    const progressBar = document.getElementById('imageUploadProgressBar');

    previewImg.src = URL.createObjectURL(file);
    previewContainer.classList.remove('hidden');
    progressBar.style.width = '0%';
    progressBar.classList.remove('bg-success', 'bg-danger');
    state.postCreation.imageData = null;

    try {
        const sigData = await apiFetch('/utils/cloudinary-signature');

        const formData = new FormData();
        formData.append('file', file);
        formData.append('api_key', sigData.api_key);
        formData.append('timestamp', sigData.timestamp);
        formData.append('signature', sigData.signature);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `https://api.cloudinary.com/v1_1/${sigData.cloud_name}/image/upload`, true);

        xhr.upload.onprogress = function(event) {
            if (event.lengthComputable) {
                const percentComplete = (event.loaded / event.total) * 100;
                progressBar.style.width = percentComplete + '%';
            }
        };
        xhr.onload = function() {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                state.postCreation.imageData = {
                    url: response.secure_url,
                    public_id: response.public_id,
                    height: response.height,
                    width: response.width
                };
                showStatus('Image uploaded successfully!', 'success');
                progressBar.classList.add('bg-success');
            } else {
                showStatus(`Image upload failed: ${JSON.parse(xhr.responseText).error.message}`, 'danger');
                progressBar.classList.add('bg-danger');
                previewContainer.classList.add('hidden');
            }
        };
        xhr.onerror = function() {
            showStatus('An error occurred during the upload.', 'danger');
            previewContainer.classList.add('hidden');
        };
        xhr.send(formData);
    } catch (error) {
        showStatus('Could not prepare image for upload. Please try again.', 'danger');
        previewContainer.classList.add('hidden');
    }
}

async function finalizePostCreation() {
    const btn = document.querySelector('#createPostModal [data-action="submit-post"]');
    const creator = btn.closest('.modal-content');
    const circle_id = creator.querySelector('.circleSelect').value;

    const postType = state.postCreation.type;
    const tags = creator.querySelector('.postTags').value
        .split(',')
        .map(t => t.trim())
        .filter(Boolean);

    let payload = {
        tags,
        is_chat_enabled: state.postCreation.chat.is_enabled,
        chat_participant_ids: state.postCreation.chat.participant_ids
    };
    let postTypeForApi;
    try {
        switch (postType) {
            case 'main':
                {
                    const text = creator.querySelector('.post-main-input').value.trim();
                    if (!text) throw new Error('Post content cannot be empty.');
                    postTypeForApi = 'standard';
                    payload.text = text;
                    break;
                }
            case 'wishlist':
                {
                    postTypeForApi = 'wishlist';
                    const title = creator.querySelector('.wishlistTitleInput').value.trim();
                    if (!title) throw new Error('A title for your wishlist is required.');
                    const urls = state.postCreation.wishlist.urls;
                    if (urls.length === 0) throw new Error('Please add at least one link to your wishlist.');
                    payload.text = title;
                    payload.wishlist_data = urls.map(url => ({
                        url,
                        title: new URL(url).hostname
                    }));
                    break;
                }
            case 'playlist':
                {
                    postTypeForApi = 'yt-playlist';
                    const playlistName = creator.querySelector('.playlistNameInput').value.trim();
                    if (!playlistName) throw new Error('Playlist name is required.');
                    const selectedVideos = state.postCreation.playlist.videos;
                    if (selectedVideos.length === 0) throw new Error('Playlist must have at least one video.');
                    payload.playlist_data = {
                        name: playlistName,
                        videos: selectedVideos
                    };
                    break;
                }
            case 'poll':
                {
                    postTypeForApi = 'poll';
                    const question = state.postCreation.pollData.question.trim();
                    const options = state.postCreation.pollData.options.map(opt => opt.trim()).filter(Boolean);
                    if (!question) throw new Error('Please enter a poll question.');
                    if (options.length < 2) throw new Error('Please provide at least two poll options.');
                    const durationHours = parseInt(creator.querySelector('#pollDurationSelect').value, 10);
                    if (!durationHours || durationHours <= 0) throw new Error('Please select a valid poll duration.');
                    payload.poll_data = {
                        question,
                        options: options.map(text => ({
                            text
                        }))
                    };
                    payload.poll_duration_hours = durationHours;
                    break;
                }
            case 'image':
                {
                    postTypeForApi = 'image';
                    const caption = creator.querySelector('#imageCaptionInput').value.trim();
                    
                    // Corrected Logic: Only check for an image uploaded to the state.
                    if (!state.postCreation.imageData) {
                        throw new Error('Please wait for the image to finish uploading.');
                    }

                    // The image data is from the successful upload. Just add the caption.
                    payload.image_data = { ...state.postCreation.imageData,
                        caption
                    };
                    break;
                }
            case 'spotify_playlist':
                {
                    postTypeForApi = 'spotify_playlist';
                    const url = creator.querySelector('#spotifyUrlInput').value.trim();
                    if (!url.includes('open.spotify.com/playlist/')) {
                        throw new Error('Please enter a valid Spotify playlist URL.');
                    }
                    payload.link = url;
                    break;
                }
        }
    } catch (err) {
        showStatus(err.message, 'warning');
        return;
    }

    payload.post_type = postTypeForApi;
    setButtonLoading(btn, true);

    try {
        await apiFetch(`/circles/${circle_id}/posts`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        showStatus('Post created!', 'success');

        bootstrap.Modal.getInstance('#createPostModal') ?.hide();

        if (state.circleView.currentCircle && state.circleView.currentCircle._id === circle_id) {
            await resetAndRenderCircleFeed(circle_id);
        } else {
            await resetAndRenderDashboardFeed();
        }
    } catch (error) {
        showStatus(error.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}

async function handleCreatePost(btn) {
    const creator = btn.closest('.modal-content');
    const circle_id = creator.querySelector('.circleSelect').value;
    if (!circle_id) {
        return showStatus('You must select a circle to post in.', 'warning');
    }
    state.postCreation.chat.is_enabled = creator.querySelector('#enableChatSwitch').checked;

    if (state.postCreation.chat.is_enabled) {
        openChatParticipantSelector(circle_id, 'create');
    } else {
        state.postCreation.chat.participant_ids = [];
        await finalizePostCreation();
    }
}

async function openChatParticipantSelector(circleId, context = 'create', existingParticipantIds = []) {
    const modal = bootstrap.Modal.getOrCreateInstance('#chatParticipantSelectorModal');
    const container = document.getElementById('chatParticipantList');
    const confirmBtn = document.querySelector('#chatParticipantSelectorModal [data-action="confirm-chat-participants"]');

    confirmBtn.dataset.context = context;
    container.innerHTML = `<div class="p-4 text-center"><span class="spinner-border spinner-border-sm"></span></div>`;
    modal.show();

    try {
        const circle = await apiFetch(`/circles/${circleId}`);
        const members = circle.members.filter(m => m.user_id !== state.currentUser._id);

        if (members.length === 0) {
            container.innerHTML = `<div class="p-4 text-center small">There are no other members in this circle to add to a chat.</div>`;
            confirmBtn.disabled = true;
            return;
        }

        confirmBtn.disabled = false;
        container.innerHTML = members.map(member => {
            const isChecked = (context === 'create') || existingParticipantIds.includes(member.user_id);
            return `
                  <div class="form-check">
                    <input class="form-check-input" type="checkbox" value="${member.user_id}" id="chat-member-${member.user_id}" ${isChecked ? 'checked' : ''}>
                    <label class="form-check-label" for="chat-member-${member.user_id}">
                      <img src="${generateAvatarUrl(member.username)}" class="avatar-small me-2">
                      ${member.username}
                    </label>
                  </div>`;
        }).join('');
    } catch (error) {
        container.innerHTML = `<div class="p-4 text-center text-danger">Could not load circle members.</div>`;
    }
}


async function handleDeletePost(postId, circleId) {
    if (!confirm('Are you sure you want to permanently delete this post?')) return;
    try {
        await apiFetch(`/circles/${circleId}/posts/${postId}`, {
            method: 'DELETE'
        });
        showStatus('Post deleted.', 'success');
        const postElement = document.querySelector(`.post-card-wrapper[data-post-id="${postId}"]`);
        if (postElement) {
            postElement.remove();
        }
    } catch (error) {
        // The error is already shown by apiFetch
    }
}

async function handleShowSeenStatus(postId) {
    const modal = bootstrap.Modal.getOrCreateInstance('#seenStatusModal');
    const seenList = document.getElementById('seenUserList');
    const unseenList = document.getElementById('unseenUserList');

    seenList.innerHTML = `<div class="spinner-border spinner-border-sm"></div>`;
    unseenList.innerHTML = `<div class="spinner-border spinner-border-sm"></div>`;
    modal.show();

    try {
        const data = await apiFetch(`/posts/${postId}/seen-status`);
        const renderUsers = (users) => {
            if (users.length === 0) return '<li class="list-group-item ">None</li>';
            return users.map(user => `
<li class="list-group-item d-flex align-items-center">
<img src="${generateAvatarUrl(user.username)}" class="avatar-small me-3">
<span>${user.username}</span>
</li>
`).join('');
        };
        seenList.innerHTML = renderUsers(data.seen);
        unseenList.innerHTML = renderUsers(data.unseen);
    } catch (error) {
        showStatus('Could not load seen status for this post.', 'danger');
        seenList.innerHTML = '<li class="list-group-item text-danger">Error loading data</li>';
        unseenList.innerHTML = '<li class="list-group-item text-danger">Error loading data</li>';
    }
}

// -----------------------------------------------
// Post Editing Logic
// -----------------------------------------------
function handleOpenEditModal(postId, circleId) {
    const post = state.dashboardFeed.posts.find(p => p._id === postId) || state.circleView.posts.find(p => p._id === postId);
    if (!post) {
        showStatus('Could not find the post data to edit.', 'danger');
        return;
    }

    const modalEl = document.getElementById('editPostModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

    // Store original data for comparison when saving
    state.postEditing = {
        postId,
        circleId,
        originalPost: post,
        participant_ids: (post.chat_participants || []).map(p => p.user_id)
    };

    // Get references to modal elements using their unique IDs for reliability
    const form = document.getElementById('editPostForm');
    const contentContainer = document.getElementById('editPostContentContainer');
    const textInputContainer = document.getElementById('editPostTextContainer');
    const tagsInputContainer = document.getElementById('editPostTagsContainer');

    // Reset form state before populating
    contentContainer.innerHTML = '';
    textInputContainer.classList.add('hidden');
    tagsInputContainer.classList.remove('hidden'); // Tags are usually editable

    // Populate common fields that apply to all post types
    form.querySelector('#editPostId').value = postId;
    form.querySelector('#editCircleId').value = circleId;
    form.querySelector('#editPostTags').value = (post.content.tags || []).join(', ');
    const chatSwitch = form.querySelector('#editEnableChatSwitch');
    chatSwitch.checked = post.is_chat_enabled;
    form.querySelector('#editChatOptionsContainer').classList.toggle('hidden', !chatSwitch.checked);

    // Populate type-specific fields based on the post's content
    const postType = post.content.post_type || 'standard';
    switch (postType) {
        case 'standard':
            textInputContainer.classList.remove('hidden');
            form.querySelector('#editPostText').value = post.content.text || '';
            break;

        case 'wishlist':
            contentContainer.innerHTML = `
                  <div class="mb-3">
                      <label for="editWishlistTitle" class="form-label">Wishlist Title</label>
                      <input type="text" id="editWishlistTitle" class="form-control" value="${post.content.text || ''}">
                  </div>
                  <label class="form-label">Items</label>
                  <div id="editWishlistItemsContainer" style="max-height: 30vh; overflow-y: auto;">
                      ${(post.content.wishlist_data || []).map((item) => `
                          <div class="input-group input-group-sm mb-2">
                              <input type="url" class="form-control edit-wishlist-item-input" value="${item.url}" placeholder="https://...">
                              <button class="btn btn-outline-danger" type="button" data-action="edit-remove-wishlist-item"><i class="bi bi-trash"></i></button>
                          </div>
                      `).join('')}
                  </div>
                  <button type="button" class="btn btn-sm btn-outline-success mt-2" data-action="edit-add-wishlist-item"><i class="bi bi-plus-circle"></i> Add Item</button>
            `;
            break;

        case 'yt-playlist':
            // Dynamically create the full editing UI for playlists, including add controls
            contentContainer.innerHTML = `
                  <div class="mb-3">
                      <label for="editPlaylistName" class="form-label">Playlist Name</label>
                      <input type="text" id="editPlaylistName" class="form-control" value="${post.content.playlist_data.name || ''}">
                  </div>
                  <div class="input-group mb-3">
                    <input type="url" id="editYoutubeUrlInput" class="form-control" placeholder="Or paste a YouTube video URL here...">
                    <button class="btn btn-primary" type="button" data-action="add-yt-video-from-url">
                      <i class="bi bi-plus-lg"></i> Add
                    </button>
                  </div>
                  <button class="btn btn-secondary btn-sm mb-2" data-action="open-yt-search">
                    <i class="bi bi-binoculars-fill"></i> Find Videos
                  </button>
                  <div class="selectedPlaylistVideosContainer mt-2" id="editPlaylistVideosContainer" data-videos="[]" style="max-height: 25vh; overflow-y: auto;">
                  </div>
            `;
            const editContainer = modalEl.querySelector('#editPlaylistVideosContainer');
            const initialVideos = [...(post.content.playlist_data.videos || [])];
            // Render the initial list of videos directly into the new container
            renderSelectedPlaylistVideos(editContainer, initialVideos);
            break;

        default:
            tagsInputContainer.classList.add('hidden');
            contentContainer.innerHTML = `<div class="alert alert-info small">This post type cannot be edited. You can only manage its tags and chat settings.</div>`;
            break;
    }

    modal.show();
}


async function handleSavePostEdits(btn) {
    const {
        postId,
        circleId,
        originalPost
    } = state.postEditing;
    if (!postId || !circleId || !originalPost) {
        showStatus('Error: Post editing context is missing.', 'danger');
        return;
    }

    const form = document.getElementById('editPostForm');
    const postType = originalPost.content.post_type || 'standard';

    // NEW VALIDATION LOGIC STARTS HERE
    // =================================================================
    // Before doing anything else, check if the edit results in an empty post.
    let isEmpty = false;
    let postTypeName = '';

    switch (postType) {
        case 'yt-playlist':
            const videoContainer = form.querySelector('#editPlaylistVideosContainer');
            const newVideos = JSON.parse(videoContainer.dataset.videos || '[]');
            if (newVideos.length === 0) {
                isEmpty = true;
                postTypeName = 'playlist';
            }
            break;

        case 'wishlist':
            const itemInputs = form.querySelectorAll('.edit-wishlist-item-input');
            const newUrls = Array.from(itemInputs).map(input => input.value.trim()).filter(Boolean);
            if (newUrls.length === 0) {
                isEmpty = true;
                postTypeName = 'wishlist';
            }
            break;
    }

    if (isEmpty) {
        const confirmationMessage = `You've removed all items from this ${postTypeName}. An empty ${postTypeName} isn't very useful.\n\nDo you want to DELETE this post instead?`;
        if (confirm(confirmationMessage)) {
            // User confirmed deletion
            bootstrap.Modal.getInstance('#editPostModal').hide();
            await handleDeletePost(postId, circleId); // Reuse your existing delete function
        }
        // Whether they confirm or cancel, we stop the save process.
        return;
    }
    // =================================================================
    // END OF NEW VALIDATION LOGIC

    const payload = {};

    // 1. Compare and collect changes for tags
    const newTags = form.querySelector('#editPostTags').value.split(',').map(t => t.trim()).filter(Boolean);
    const originalTags = originalPost.content.tags || [];
    if (JSON.stringify(newTags.sort()) !== JSON.stringify(originalTags.sort())) {
        payload.tags = newTags;
    }

    // 2. Compare and collect changes for chat settings
    const newIsChatEnabled = form.querySelector('#editEnableChatSwitch').checked;
    if (newIsChatEnabled !== originalPost.is_chat_enabled) {
        payload.is_chat_enabled = newIsChatEnabled;
    }
    const originalParticipantIds = (originalPost.chat_participants || []).map(p => p.user_id);
    if (JSON.stringify(state.postEditing.participant_ids.sort()) !== JSON.stringify(originalParticipantIds.sort())) {
        payload.chat_participant_ids = state.postEditing.participant_ids;
    }

    // 3. Compare and collect content changes based on the post type
    switch (postType) {
        case 'standard':
            const newText = form.querySelector('#editPostText').value;
            if (newText !== (originalPost.content.text || '')) {
                payload.text = newText;
            }
            break;

        case 'wishlist':
            const newTitle = form.querySelector('#editWishlistTitle').value;
            const itemInputs = form.querySelectorAll('.edit-wishlist-item-input');
            const newUrls = Array.from(itemInputs).map(input => ({
                url: input.value.trim()
            })).filter(item => item.url);
            const originalTitle = originalPost.content.text || '';
            const originalUrls = (originalPost.content.wishlist_data || []).map(item => ({
                url: item.url
            }));

            if (newTitle !== originalTitle || JSON.stringify(newUrls) !== JSON.stringify(originalUrls)) {
                payload.text = newTitle;
                payload.wishlist_data = newUrls;
            }
            break;

        case 'yt-playlist':
            const newPlaylistName = form.querySelector('#editPlaylistName').value;
            const videoContainer = form.querySelector('#editPlaylistVideosContainer');
            const newVideos = JSON.parse(videoContainer.dataset.videos || '[]');
            const originalPlaylistData = originalPost.content.playlist_data || {
                name: '',
                videos: []
            };

            if (newPlaylistName !== originalPlaylistData.name || JSON.stringify(newVideos) !== JSON.stringify(originalPlaylistData.videos)) {
                payload.playlist_data = {
                    name: newPlaylistName,
                    videos: newVideos
                };
            }
            break;
    }

    // 4. If nothing changed, just close the modal without an API call
    if (Object.keys(payload).length === 0) {
        bootstrap.Modal.getInstance('#editPostModal').hide();
        showStatus('No changes were made.', 'info');
        return;
    }

    // 5. Send the PATCH request to the server with only the changed data
    setButtonLoading(btn, true);
    try {
        await apiFetch(`/circles/${circleId}/posts/${postId}`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
        showStatus('Post updated successfully!', 'success');
        bootstrap.Modal.getInstance('#editPostModal').hide();

        // Refresh the current view to show the changes
        if (!dom.circleView.classList.contains('hidden')) {
            await resetAndRenderCircleFeed(circleId);
        } else {
            await resetAndRenderDashboardFeed();
        }
    } catch (error) {
        console.error("Failed to save post edits:", error);
    } finally {
        setButtonLoading(btn, false);
    }
}

// -----------------------------------------------
// Invite to circle:
async function handleInviteToCircle(circleId) {
    const inviteModalEl = document.getElementById('inviteCircleModal');
    const inviteModal = bootstrap.Modal.getOrCreateInstance(inviteModalEl);
    const qrContainer = document.getElementById('qrCodeContainer');
    const linkInput = document.getElementById('inviteLinkInput');

    inviteModalEl.dataset.circleId = circleId;

    qrContainer.innerHTML = `<div class="spinner-border text-primary" role="status"></div>`;
    linkInput.value = '';
    document.getElementById('directInviteUsernameInput').value = '';
    inviteModal.show();

    try {
        const {
            token
        } = await apiFetch(`/circles/${circleId}/invite-token`, {
            method: 'POST'
        });
        const url = `${window.location.origin}${window.location.pathname}#/join-circle/${token}`;
        linkInput.value = url;
        const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;
        qrContainer.innerHTML = `<img src="${qrUrl}" alt="Circle Invite QR Code">`;
    } catch (error) {
        showStatus('Could not create invite link.', 'danger');
        inviteModal.hide();
    }
}

async function handleJoinByToken(token, isRedirect = false) {
    if (!state.currentUser) {
        localStorage.setItem('pendingInviteToken', token);
        showStatus('Please log in or register to accept the circle invite.', 'info');
        if (window.location.hash) {
            window.location.hash = '';
        } else {
            handleRoute();
        }
        return;
    }
    try {
        const {
            circle_id,
            circle_name
        } = await apiFetch('/circles/join-by-token', {
            method: 'POST',
            body: JSON.stringify({
                token
            })
        });
        showStatus(`Successfully joined the circle: ${circle_name}!`, 'success');
        await fetchAndRenderAll();
        window.location.hash = `#/circle/${circle_id}`;
    } catch (error) {
        console.error("Failed to join by token:", error);
        if (!isRedirect) window.location.hash = '';
    }
}

// -----------------------------------------------
// Comments & Poll Voting
async function handleOpenCommentsModal(postId, postAuthorUsername) {
    if (state.newActivityPostIds.has(postId)) {
        state.newActivityPostIds.delete(postId);
        const postCard = document.querySelector(`.post-card[data-post-id="${postId}"]`);
        if (postCard) {
            postCard.classList.remove('has-new-activity');
        }
    }

    const modal = bootstrap.Modal.getOrCreateInstance('#commentsModal');
    const originalPostContainer = document.getElementById('originalPostContainer');
    const commentsContainer = document.getElementById('commentsContainer');
    const commentForm = document.getElementById('commentForm');

    commentForm.dataset.postId = postId;
    commentForm.dataset.postAuthorUsername = postAuthorUsername;
    delete commentForm.dataset.threadUserId;

    originalPostContainer.innerHTML = '';
    commentsContainer.innerHTML = '<div class="spinner-border spinner-border-sm"></div>';
    modal.show();

    const isAuthor = state.currentUser.username === postAuthorUsername;
    const postContentHtml = getSanitizedPostContent(postId);
    originalPostContainer.innerHTML = postContentHtml;

    try {
        if (isAuthor) {
            const commenters = await apiFetch(`/posts/${postId}/commenters`);
            renderCommenterList(postId, commenters);
        } else {
            const comments = await apiFetch(`/posts/${postId}/comments`);
            renderComments(comments, postId);
        }
    } catch (e) {
        commentsContainer.innerHTML = `<div class="text-danger small mt-2">${e.message}</div>`;
    }
}

function renderCommenterList(postId, commenters) {
    const container = document.getElementById('commentsContainer');
    document.getElementById('commentForm').classList.add('hidden');
    if (commenters.length === 0) {
        container.innerHTML = '<p class="text-center">No one has commented on this post yet.</p>';
        return;
    }
    container.innerHTML = `
<p class="small">Select a user to view their comment thread:</p>
<div class="list-group">
${commenters.map(c => `
<a href="#"
class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
data-action="view-comment-thread"
data-post-id="${postId}"
data-commenter-id="${c.user_id}"
data-commenter-username="${c.username}">
<div>
<img src="${generateAvatarUrl(c.username)}" class="avatar-small me-2">
${c.username}
</div>
<span class="badge ${c.has_unread ? 'bg-danger' : 'bg-primary'} rounded-pill">
${c.comment_count}
${c.has_unread ? '<i class="bi bi-bell-fill ms-1"></i>' : ''}
</span>
</a>
`).join('')}
</div>
`;
}

async function handleViewCommentThread(postId, commenterId, commenterUsername) {
    const container = document.getElementById('commentsContainer');
    const commentForm = document.getElementById('commentForm');
    commentForm.dataset.threadUserId = commenterId;
    commentForm.classList.remove('hidden');
    commentForm.querySelector('textarea').placeholder = `Replying to ${commenterUsername}...`;
    container.innerHTML = '<div class="spinner-border spinner-border-sm"></div>';
    try {
        const comments = await apiFetch(`/posts/${postId}/comments?thread_user_id=${commenterId}`);
        renderComments(comments, postId, true);
    } catch (e) {
        container.innerHTML = '<div class="text-danger">Could not load this thread.</div>';
    }
}

function renderComments(comments, postId, isAuthorViewing = false) {
    const container = document.getElementById('commentsContainer');
    const commentForm = document.getElementById('commentForm');
    commentForm.classList.remove('hidden');

    if (!isAuthorViewing) {
        commentForm.querySelector('textarea').placeholder = 'Add a comment...';
    }

    const backButtonHtml = isAuthorViewing ?
        `<button class="btn btn-sm btn-secondary mb-3"
data-action="open-comments"
data-post-id="${postId}"
data-post-author-username="${state.currentUser.username}">
<i class="bi bi-arrow-left"></i> Back to Threads
</button>` :
        '';

    let commentsHtmlContent = '';
    if (comments.length === 0) {
        commentsHtmlContent = isAuthorViewing ?
            '<p class="text-center mt-3">No comments in this thread yet.</p>' :
            '<p class="text-center mt-3">Be the first to comment.</p>';
    } else {
        commentsHtmlContent = comments.map(comment => {
            const isCurrentUser = comment.commenter_username === state.currentUser.username;
            return `
<div class="comment-bubble ${isCurrentUser ? 'current-user' : ''}">
<div class="d-flex justify-content-between align-items-center mb-1">
<div>
<img src="${generateAvatarUrl(comment.commenter_username)}" class="avatar-small me-2">
<strong>${isCurrentUser ? 'You' : comment.commenter_username}</strong>
</div>
${
isCurrentUser
? `<button class="btn btn-sm btn-link text-danger p-0"
data-action="delete-comment"
data-comment-id="${comment._id}"
data-post-id="${postId}">
<i class="bi bi-trash"></i>
</button>`
: ''
}
</div>
<p class="mb-1" style="white-space: pre-wrap;">${comment.content}</p>
<small class="">${new Date(comment.created_at).toLocaleString()}</small>
</div>
`;
        }).join('');
    }
    container.innerHTML = backButtonHtml + commentsHtmlContent;
    container.scrollTop = container.scrollHeight;
}

async function handlePollVote(postId, optionIndex) {
    try {
        const {
            poll_results
        } = await apiFetch(`/posts/${postId}/poll-vote`, {
            method: 'POST',
            body: JSON.stringify({
                option_index: optionIndex
            })
        });
        const postWrapper = document.querySelector(`[data-post-wrapper-id="${postId}"]`);
        if (postWrapper) {
            const totalVotes = poll_results.total_votes;
            const userVotedIndex = poll_results.user_voted_index;
            postWrapper.querySelectorAll('.poll-option').forEach((el, idx) => {
                const optionData = poll_results.options[idx];
                const percentage = totalVotes > 0 ? (optionData.votes / totalVotes) * 100 : 0;
                el.classList.toggle('voted-by-user', userVotedIndex === idx);
                el.querySelector('.progress').style.width = `${percentage}%`;
                el.querySelector('.d-flex span:last-child').textContent = `${percentage.toFixed(0)}% (${optionData.votes})`;

                if (el.querySelector('.bi-check-circle-fill')) {
                    el.querySelector('.bi-check-circle-fill').remove();
                }
                if (userVotedIndex === idx) {
                    el.querySelector('.d-flex span:first-child')
                        .insertAdjacentHTML('beforeend', ' <i class="bi bi-check-circle-fill"></i>');
                }
            });
            const footer = postWrapper.querySelector('.poll-container + small');
            if (footer) {
                const timePart = footer.innerHTML.includes('') ?
                    footer.innerHTML.split('')[1] :
                    '';
                footer.innerHTML = `Total votes: ${totalVotes} ${timePart ? `${timePart}` : ''}`;
            }
        }
    } catch (e) {
        showStatus(e.message, 'danger');
    }
}

// -----------------------------------------------
// Chat Modal Logic
async function handleOpenChatModal(postId) {
    const modalEl = document.getElementById('chatModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const messagesContainer = document.getElementById('chatMessagesContainer');
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');

    chatForm.dataset.postId = postId;

    messagesContainer.innerHTML = `<div class="p-5 text-center"><div class="spinner-border text-primary" role="status"></div></div>`;
    modal.show();

    try {
        const messages = await apiFetch(`/posts/${postId}/chat`);
        renderChatMessages(messages, messagesContainer);
    } catch (error) {
        messagesContainer.innerHTML = `<div class="p-4 text-center text-danger">Could not load chat messages.</div>`;
    }

    chatInput.focus();
}

function renderChatMessages(messages, container) {
    if (messages.length === 0) {
        container.innerHTML = `<div class="p-4 text-center small text-muted">No messages in this chat yet. Be the first to say something!</div>`;
        return;
    }
    container.innerHTML = messages.map(msg => createChatMessageHtml(msg)).join('');
    container.scrollTop = container.scrollHeight;
}

function appendChatMessage(message, container) {
    const placeholder = container.querySelector('.text-muted');
    if (placeholder) {
        container.innerHTML = '';
    }
    container.insertAdjacentHTML('beforeend', createChatMessageHtml(message));
    container.scrollTop = container.scrollHeight;
}

function createChatMessageHtml(message) {
    if (!state.currentUser) return '';
    const isCurrentUser = message.sender_id === state.currentUser._id;
    return `
       <div class="chat-bubble-wrapper ${isCurrentUser ? 'current-user' : ''}">
         <div class="chat-bubble">
       ${!isCurrentUser ? `
          <div class="chat-bubble-header">
            <img src="${generateAvatarUrl(message.sender_username)}" class="avatar-small me-2">
            <strong>${message.sender_username}</strong>
          </div>`
       : ''}
       <p class="chat-bubble-content mb-1" style="white-space: pre-wrap;">${message.content}</p>
       <small class="chat-bubble-timestamp">${new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small>
         </div>
       </div>
     `;
}


// -----------------------------------------------
// YouTube Playlist Player logic (unchanged):
let ytPlaylistPlayer = null;

function openPlaylistPlayerModal(playlist) {
    if (!playlist || !playlist.videos || playlist.videos.length === 0) {
        showStatus("This playlist is empty or invalid.", "warning");
        return;
    }
    const playlistPlayerModal = bootstrap.Modal.getOrCreateInstance(
        document.getElementById('playlistPlayerModal')
    );
    document.getElementById('playlistPlayerModalLabel').textContent = playlist.name;
    playlistPlayerModal.show();

    const videoIds = playlist.videos.map(v => v.id);

    const updateUI = () => {
        if (!ytPlaylistPlayer || typeof ytPlaylistPlayer.getPlaylistIndex !== 'function') return;
        const queueList = document.getElementById('playlist-queue-list');
        const infoSpan = document.getElementById('playlist-info-span');
        if (!queueList || !infoSpan) return;

        const currentIndex = ytPlaylistPlayer.getPlaylistIndex();
        const totalVideos = ytPlaylistPlayer.getPlaylist().length;
        infoSpan.textContent = `Video ${currentIndex + 1} of ${totalVideos}`;

        queueList.innerHTML = playlist.videos.map((video, index) => {
            const isActive = index === currentIndex ? 'active' : '';
            return `
<div class="playlist-queue-item list-group-item d-flex align-items-center gap-3 ${isActive}"
data-index="${index}">
<span class="fw-bold">${index + 1}</span>
<img src="${video.imageSrc}" width="100" class="rounded" alt="${video.title}">
<div class="flex-grow-1" style="min-width: 0;">
<p class="mb-0 small fw-bold text-truncate">${video.title}</p>
</div>
</div>
`;
        }).join('');

        const activeItem = queueList.querySelector('.active');
        if (activeItem) {
            activeItem.scrollIntoView({
                behavior: 'smooth',
                block: 'nearest'
            });
        }
    };

    const onPlayerStateChange = (event) => {
        if (event.data === YT.PlayerState.PLAYING) {
            updateUI();
        }
    };

    const onPlayerReady = (event) => {
        event.target.loadPlaylist(videoIds);
        updateUI();
    };

    if (ytPlaylistPlayer && typeof ytPlaylistPlayer.loadPlaylist === 'function') {
        ytPlaylistPlayer.loadPlaylist(videoIds);
    } else {
        ytPlaylistPlayer = new YT.Player('playlist-player-embed', {
            height: '100%',
            width: '100%',
            playerVars: {
                'autoplay': 1,
                'controls': 1,
                'rel': 0,
                'modestbranding': 1
            },
            events: {
                'onReady': onPlayerReady,
                'onStateChange': onPlayerStateChange
            }
        });
    }
}

function showYoutubeSearchLoading(container) {
    container.innerHTML = Array.from({
        length: 3
    }, () => `
<div class="yt-search-result-skeleton"></div>
`).join('');
}

async function handleYouTubeSearch(btn) {
    const query = document.getElementById('youtubeSearchInput').value.trim();
    const container = document.getElementById('youtubeSearchResultsContainer');
    if (!query) return;
    setButtonLoading(btn, true);
    showYoutubeSearchLoading(container);

    try {
        const results = await ytApp.search(query);
        renderYouTubeSearchResults(results);
    } catch (e) {
        container.innerHTML = `<p class="text-danger small">${e.message}</p>`;
    } finally {
        setButtonLoading(btn, false);
    }
}

function renderYouTubeSearchResults(results) {
    const container = document.getElementById('youtubeSearchResultsContainer');
    if (!results || results.length === 0) {
        container.innerHTML = '<p class="small text-center">No videos found.</p>';
        return;
    }
    const addedVideoIds = new Set(
        state.postCreation.playlist.videos.map(v => v.id)
    );
    container.innerHTML = results.map(video => {
        const isAdded = addedVideoIds.has(video.id);
        const videoData = JSON.stringify(video).replace(/'/g, "'");
        return `
<div class="yt-search-result d-flex justify-content-between align-items-center">
<div class="d-flex align-items-center" style="overflow: hidden;">
<img src="${video.imageSrc}" width="80" class="me-2 rounded" alt="thumbnail">
<small class="text-truncate">${video.title}</small>
</div>
<button type="button" class="btn ${isAdded ? 'btn-success' : 'btn-primary'} btn-sm py-0"
data-action="add-video-to-playlist"
data-video='${videoData}'
${isAdded ? 'disabled' : ''}>
${isAdded ? 'Added' : '<i class="bi bi-plus-lg"></i>'}
</button>
</div>
`;
    }).join('');
}

function renderSelectedPlaylistVideos(container, videos) {
    if (!container) return;

    if (videos.length === 0) {
        container.innerHTML = '<p class="small text-center">Added videos will appear here. You can drag to reorder.</p>';
    } else {
        container.innerHTML = videos.map(video => `
              <div class="yt-selected-video d-flex justify-content-between align-items-center"
              draggable="true" data-video-id="${video.id}">
              <div class="d-flex align-items-center" style="overflow: hidden;">
                  <i class="bi bi-grip-vertical me-2"></i>
                  <img src="${video.imageSrc}" width="80" class="me-2 rounded" alt="thumbnail">
                  <small class="text-truncate">${video.title}</small>
              </div>
              <button type="button" class="btn btn-danger btn-sm py-0"
                  data-action="remove-video-from-playlist"
                  data-video-id="${video.id}">
                  <i class="bi bi-trash"></i>
              </button>
              </div>
          `).join('');
    }
    // This attribute is the source of truth for saving edits and for other actions
    container.dataset.videos = JSON.stringify(videos);
}

// Reorder logic:
let draggedItem = null;
document.addEventListener('dragstart', (e) => {
    if (e.target.classList.contains('yt-selected-video')) {
        draggedItem = e.target;
        setTimeout(() => e.target.classList.add('dragging'), 0);
    }
});
document.addEventListener('dragend', (e) => {
    if (e.target.classList.contains('yt-selected-video')) {
        setTimeout(() => {
            draggedItem.classList.remove('dragging');
            draggedItem = null;
            const container = e.target.closest('.selectedPlaylistVideosContainer');
            if (!container) return;
            const videoElements = [...container.querySelectorAll('.yt-selected-video')];
            const newVideosOrder = videoElements.map(el =>
                state.postCreation.playlist.videos.find(v => v.id === el.dataset.videoId)
            );
            state.postCreation.playlist.videos = newVideosOrder;
            container.dataset.videos = JSON.stringify(newVideosOrder);
        }, 0);
    }
});
document.addEventListener('dragover', e => {
    e.preventDefault();
    const container = e.target.closest('.selectedPlaylistVideosContainer');
    if (container && draggedItem) {
        const afterElement = [...container.querySelectorAll('.yt-selected-video:not(.dragging)')]
            .reduce((closest, child) => {
                const box = child.getBoundingClientRect();
                const offset = e.clientY - box.top - box.height / 2;
                return (offset < 0 && offset > closest.offset) ? {
                    offset,
                    element: child
                } :
                    closest;
            }, {
                offset: Number.NEGATIVE_INFINITY
            }).element;
        if (afterElement == null) {
            container.appendChild(draggedItem);
        } else {
            container.insertBefore(draggedItem, afterElement);
        }
    }
});

// -----------------------------------------------
// Circle Management:
async function handleOpenManageCircle(circleId) {
    const manageModal = bootstrap.Modal.getOrCreateInstance('#manageCircleModal');
    manageModal.show();
    try {
        const circleData = await apiFetch(`/circles/${circleId}`);
        renderCircleManagementUI(circleData);
    } catch (e) {
        showStatus('Could not load circle management details.', 'danger');
        manageModal.hide();
    }
}


function renderCircleManagementUI(circle) {
    document.getElementById('manageCircleId').value = circle._id;
    document.getElementById('manageCircleName').value = circle.name;
    document.getElementById('manageCircleDescription').value = circle.description || '';

    document.getElementById('manageCircleIsPublic').checked = circle.is_public;

    const membersContainer = document.getElementById('manageCircleMembersContainer');
    if (!circle.members || circle.members.length === 0) {
        membersContainer.innerHTML = '<p class="text-center p-3">No member data available.</p>';
    } else {
        const currentUserRole = circle.user_role;
        membersContainer.innerHTML = circle.members.map(member => {
            let actionButtons = '';
            const canManage = (
                (currentUserRole === 'admin' && member.role !== 'admin') ||
                (currentUserRole === 'moderator' && member.role === 'member')
            );

            if (canManage && member.user_id !== state.currentUser._id) {
                if (member.role === 'member') {
                    actionButtons += `
               <button class="btn btn-sm btn-success"
                  data-action="manage-member-role"
                  data-user-id="${member.user_id}"
                  data-new-role="moderator">
               Promote to Mod
               </button>`;
                } else if (member.role === 'moderator') {
                    actionButtons += `
               <button class="btn btn-sm btn-secondary"
                  data-action="manage-member-role"
                  data-user-id="${member.user_id}"
                  data-new-role="member">
               Demote to Member
               </button>`;
                }
                actionButtons += `
               <button class="btn btn-sm btn-danger ms-2"
               data-action="manage-member-kick"
               data-user-id="${member.user_id}"
               data-username="${member.username}">
               Kick
               </button>`;
            }
            const roleBadge = {
                admin: 'bg-primary',
                moderator: 'bg-success',
                member: 'bg-secondary'
            } [member.role];

            return `
           <div class="list-group-item d-flex justify-content-between align-items-center">
           <div>
              <img src="${generateAvatarUrl(member.username)}" class="avatar-small me-2">
              <strong>${member.username}</strong>
              <span class="badge rounded-pill ${roleBadge} ms-2">${member.role}</span>
           </div>
           <div class="btn-group">${actionButtons}</div>
           </div>`;
        }).join('');
    }
    document.getElementById('confirmDeleteCircleName').textContent = circle.name;
    document.getElementById('deleteCircleConfirmationInput').value = '';
    document.getElementById('deleteCircleBtn').disabled = true;
}



async function handleUpdateCircleSettings(btn) {
    const circleId = document.getElementById('manageCircleId').value;
    const payload = {
        name: document.getElementById('manageCircleName').value,
        description: document.getElementById('manageCircleDescription').value
    };

    setButtonLoading(btn, true);
    try {
        await apiFetch(`/circles/${circleId}`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
        showStatus('Circle settings updated successfully!', 'success');
        bootstrap.Modal.getInstance('#manageCircleModal').hide();
        await resetAndRenderCircleFeed(circleId);
        await renderAllSidebarComponents();
    } catch (e) {
        showStatus(e.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}

async function handleManageMemberRole(btn, userId, newRole) {
    const circleId = document.getElementById('manageCircleId').value;
    if (!confirm(`Are you sure you want to change this member's role to ${newRole}?`)) return;
    setButtonLoading(btn, true);
    try {
        const updatedCircle = await apiFetch(`/circles/${circleId}/members/${userId}`, {
            method: 'PATCH',
            body: JSON.stringify({
                role: newRole
            })
        });
        showStatus('Member role updated.', 'success');
        renderCircleManagementUI(updatedCircle);
    } catch (e) {
        showStatus(e.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}

async function handleKickMember(btn, userId, username) {
    const circleId = document.getElementById('manageCircleId').value;
    if (!confirm(`Are you sure you want to kick ${username} from the circle?`)) return;
    setButtonLoading(btn, true);
    try {
        const updatedCircle = await apiFetch(`/circles/${circleId}/members/${userId}`, {
            method: 'DELETE'
        });
        showStatus(`${username} has been kicked from the circle.`, 'success');
        renderCircleManagementUI(updatedCircle);
    } catch (e) {
        showStatus(e.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}

async function handleDeleteCircle(btn) {
    const circleId = document.getElementById('manageCircleId').value;
    setButtonLoading(btn, true);
    try {
        await apiFetch(`/circles/${circleId}`, {
            method: 'DELETE'
        });
        showStatus('Circle has been permanently deleted.', 'success');
        bootstrap.Modal.getInstance('#manageCircleModal').hide();
        window.location.hash = '';
        await handleRoute();
    } catch (e) {
        showStatus(e.message, 'danger');
    } finally {
        setButtonLoading(btn, false);
    }
}

// -----------------------------------------------
// Wishlist staging area (unchanged):
const renderWishlistStagingArea = () => {
    const container = document.getElementById('wishlistStagingArea');
    if (!container) {
        console.error("Debug: Could not find 'wishlistStagingArea' in the DOM.");
        return;
    }
    const urls = state.postCreation.wishlist.urls;

    if (urls.length === 0) {
        container.innerHTML = '<div class="list-group-item small text-center">Your added items will appear here.</div>';
        return;
    }

    container.innerHTML = urls.map((url, index) => {
        try {
            const hostname = new URL(url).hostname.replace('www.', '');
            return `
<div class="list-group-item d-flex justify-content-between align-items-center"
data-index="${index}">
<div class="d-flex align-items-center text-truncate" style="min-width: 0;">
<img src="https://www.google.com/s2/favicons?domain=${hostname}&sz=32"
class="favicon me-2" alt="favicon">
<span class="url-text text-truncate">${url}</span>
<input type="text" class="form-control form-control-sm url-input hidden" value="${url}">
</div>
<div class="btn-group" style="flex-shrink: 0;">
<button class="btn btn-sm btn-secondary" data-action="edit-wishlist-item">
<i class="bi bi-pencil"></i>
</button>
<button class="btn btn-sm btn-success hidden" data-action="save-wishlist-item">
<i class="bi bi-check-lg"></i>
</button>
<button class="btn btn-sm btn-danger" data-action="remove-wishlist-item">
<i class="bi bi-trash"></i>
</button>
</div>
</div>
`;
        } catch (e) {
            return `
<div class="list-group-item d-flex justify-content-between align-items-center text-danger"
data-index="${index}">
<span class="text-truncate">Invalid URL: ${url}</span>
<button class="btn btn-sm btn-danger" data-action="remove-wishlist-item">
<i class="bi bi-trash"></i>
</button>
</div>
`;
        }
    }).join('');
};

const hideAllTooltips = () => {
    document.querySelectorAll('.tooltip').forEach(tooltip => {
        tooltip.remove();
    });
};

const initTooltips = () => {
    hideAllTooltips();

    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].forEach(tooltipTriggerEl => {
        const existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
        if (existingTooltip) {
            existingTooltip.dispose();
        }
        new bootstrap.Tooltip(tooltipTriggerEl);
    });
};

function getSanitizedPostContent(postId) {
    const postWrapper = document.querySelector(`.post-card-wrapper[data-post-id="${postId}"]`);
    const postContentElement = postWrapper ?
        postWrapper.querySelector('.post-card-body > .mt-3') :
        null;

    if (!postContentElement) {
        return `<div class="alert alert-warning small">
Could not retrieve original post content.
</div>`;
    }

    const tempDiv = postContentElement.cloneNode(true);
    tempDiv.querySelectorAll('[data-action]').forEach(el => {
        el.removeAttribute('data-action');
        el.style.pointerEvents = 'none';
        el.style.cursor = 'default';
        el.setAttribute('tabindex', '-1');

        if (el.tagName === 'A' || el.tagName === 'BUTTON') {
            el.classList.add('disabled');
        }
        if (el.classList.contains('poll-option')) {
            el.classList.add('poll-disabled');
        }
    });
    return `
<div class="original-post-content p-3 rounded border">
<h6 class="small mb-2">Original Post:</h6>
${tempDiv.innerHTML}
</div>
<hr>
`;
}

// -----------------------------------------------
// DOMContentLoaded:
document.addEventListener('DOMContentLoaded', () => {
    createNotificationsFAB();
    injectFabStyles();

    [
        '#createCircleModal',
        '#createPostModal',
        '#inviteCircleModal',
        '#playlistPlayerModal',
        '#youtubeSearchModal',
        '#manageCircleModal',
        '#seenStatusModal',
        '#commentsModal',
        '#notificationsModal',
        '#helpModal',
        '#chatParticipantSelectorModal',
        '#chatModal',
        '#editPostModal'
    ].forEach(id => {
        const modalEl = document.querySelector(id);
        if (modalEl) {
            bootstrap.Modal.getOrCreateInstance(modalEl);
        } else {
            console.warn(`Modal element with ID ${id} was not found and could not be initialized.`);
        }
    });

    initTooltips();

    document.getElementById('createCircleModal') ?.addEventListener('shown.bs.modal', () => {
        document.getElementById('circleName') ?.focus();
    });
    document.getElementById('createPostModal') ?.addEventListener('shown.bs.modal', () => {
        document.querySelector('#createTextPost textarea') ?.focus();
    });
    document.getElementById('youtubeSearchModal') ?.addEventListener('shown.bs.modal', () => {
        document.getElementById('youtubeSearchInput') ?.focus();
    });
    document.getElementById('inviteCircleModal') ?.addEventListener('shown.bs.modal', () => {
        document.getElementById('inviteLinkInput') ?.select();
    });
    document.getElementById('commentsModal') ?.addEventListener('shown.bs.modal', () => {
        document.getElementById('commentInput') ?.focus();
    });

    document.getElementById('commentForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.currentTarget.querySelector('button[type="submit"]');
        const input = document.getElementById('commentInput');
        const postId = e.currentTarget.dataset.postId;
        const postAuthorUsername = e.currentTarget.dataset.postAuthorUsername;
        const content = input.value.trim();
        if (!content || !postId) return;

        const isAuthor = state.currentUser.username === postAuthorUsername;
        const payload = {
            content
        };
        if (isAuthor && e.currentTarget.dataset.threadUserId) {
            payload.thread_user_id = e.currentTarget.dataset.threadUserId;
        }

        setButtonLoading(btn, true);
        try {
            const newComment = await apiFetch(`/posts/${postId}/comments`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            input.value = '';

            const postCard = document.querySelector(`.post-card-wrapper[data-post-id="${postId}"]`);
            const commentButton = postCard ?.querySelector(`[data-action="open-comments"]`);
            if (commentButton) {
                const currentCount = parseInt(commentButton.textContent.trim().split(' ')[1] || '0', 10);
                commentButton.innerHTML = `<i class="bi bi-chat-left-text"></i> ${currentCount + 1}`;
            }

            if (isAuthor) {
                const commenterUsername =
                    document.querySelector(`[data-action="view-comment-thread"][data-commenter-id="${newComment.thread_user_id}"]`)
                    ?.dataset.commenterUsername ||
                    'user';
                await handleViewCommentThread(postId, newComment.thread_user_id, commenterUsername);
            } else {
                const comments = await apiFetch(`/posts/${postId}/comments`);
                renderComments(comments, postId);
            }
        } catch (err) {
            showStatus(err.message, 'danger');
        } finally {
            setButtonLoading(btn, false);
        }
    });

    document.getElementById('chatForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const form = e.currentTarget;
        const postId = form.dataset.postId;
        const input = document.getElementById('chatInput');
        const content = input.value.trim();
        const btn = form.querySelector('button[type="submit"]');

        if (!content || !postId) return;

        setButtonLoading(btn, true);
        try {
            const newMessage = await apiFetch(`/posts/${postId}/chat`, {
                method: 'POST',
                body: JSON.stringify({
                    content
                })
            });
            input.value = '';
            const messagesContainer = document.getElementById('chatMessagesContainer');
            appendChatMessage(newMessage, messagesContainer);
        } catch (error) {
            // apiFetch already shows a status message
        } finally {
            setButtonLoading(btn, false);
            input.focus();
        }
    });


    const authWelcome = document.getElementById('authWelcome');
    const authFormContainer = document.getElementById('authFormContainer');

    document.getElementById('loginButton')
        .addEventListener('click', () => switchAuthView(authWelcome, authFormContainer));
    document.getElementById('backToWelcomeBtn')
        .addEventListener('click', () => switchAuthView(authFormContainer, authWelcome));
    document.getElementById('loginSubmitButton')
        .addEventListener('click', e => handleAuthAction(e, login));
    document.getElementById('registerSubmitButton')
        .addEventListener('click', e => handleAuthAction(e, register));
    document.getElementById('logoutButton')
        .addEventListener('click', logout);

    document.getElementById('createCircleBtn')
        .addEventListener('click', () =>
            bootstrap.Modal.getOrCreateInstance('#createCircleModal').show()
        );
    document.getElementById('submitCircleButton')
        .addEventListener('click', handleCreateCircle);

    const createPostModalEl = document.getElementById('createPostModal');
    const createPostModal = bootstrap.Modal.getOrCreateInstance(createPostModalEl);

    createPostModalEl.addEventListener('input', e => {
        const questionInput = e.target.closest('#pollQuestionInput');
        const optionInput = e.target.closest('.poll-option-input');

        if (questionInput) {
            state.postCreation.pollData.question = questionInput.value;
        } else if (optionInput) {
            const index = parseInt(optionInput.dataset.index, 10);
            if (!isNaN(index) && state.postCreation.pollData.options[index] !== undefined) {
                state.postCreation.pollData.options[index] = optionInput.value;
            }
        }
    });

    document.getElementById('togglePostCreatorBtn').addEventListener('click', () => {
        const select = createPostModalEl.querySelector('.circleSelect');
        const options = state.myCircles.map(c => `<option value="${c._id}">${c.name}</option>`).join('');
        select.innerHTML = `<option value="">-- Select a Circle --</option>${options}`;
        createPostModal.show();
    });

    document.body.addEventListener('click', e => {
        if (e.target.closest('#notificationsFab')) {
            openNotificationsModal();
            return;
        }

        const toggleCircleBtn = e.target.closest('#togglePostCreatorCircleBtn');
        if (toggleCircleBtn) {
            const circleId = state.circleView.currentCircle ?._id;
            const createPostModal = bootstrap.Modal.getOrCreateInstance(
                document.getElementById('createPostModal')
            );
            const select = document.getElementById('createPostModal').querySelector('.circleSelect');

            const options = state.myCircles.map(c => `
<option value="${c._id}" ${c._id === circleId ? 'selected' : ''}>${c.name}</option>
`).join('');
            select.innerHTML = `<option value="">-- Select a Circle --</option>${options}`;
            createPostModal.show();
        }
    });

    createPostModalEl.addEventListener('hidden.bs.modal', () => {
        state.postCreation = {
            type: 'main',
            playlist: {
                videos: []
            },
            linkPreview: {
                data: null,
                url: ''
            },
            imageData: null,
            pollData: {
                question: '',
                options: ['', '']
            },
            wishlist: {
                urls: []
            },
            chat: {
                is_enabled: false,
                participant_ids: []
            }
        };
        document.getElementById('poll-ai-prompt').value = '';
        document.getElementById('pollQuestionInput').value = '';
        renderPollOptionsUI();

        createPostModalEl.querySelector('.post-main-input').value = '';
        createPostModalEl.querySelector('.wishlistTitleInput').value = '';
        document.getElementById('wishlistLinkInput').value = '';
        document.getElementById('wishlistStagingArea').innerHTML = `
<div class="list-group-item small text-center">
Your added items will appear here.
</div>
`;
        createPostModalEl.querySelector('.playlistNameInput').value = '';
        createPostModalEl.querySelector('.selectedPlaylistVideosContainer').innerHTML = `
<p class="small text-center">
Added videos will appear here. You can drag to reorder.
</p>
`;
        createPostModalEl.querySelector('.postTags').value = '';

        const defaultTab = new bootstrap.Tab(
            document.querySelector('#postTypeTabs a[data-post-type="main"]')
        );
        defaultTab.show();

        document.getElementById('imageUploadPreviewContainer').classList.add('hidden');
        document.getElementById('imageFileInput').value = '';
        //document.querySelector('#createImagePost .imageUrlInput').value = '';
        document.getElementById('enableChatSwitch').checked = false;
    });

    const editPostModalEl = document.getElementById('editPostModal');
    editPostModalEl.addEventListener('hidden.bs.modal', () => {
        // Reset the editing state when the modal is closed
        state.postEditing = {
            postId: null,
            circleId: null,
            originalPost: null,
            participant_ids: []
        };
        document.getElementById('editPostForm').reset();
    });

    document.getElementById('editEnableChatSwitch').addEventListener('change', (e) => {
        const chatOptionsContainer = document.getElementById('editChatOptionsContainer');
        chatOptionsContainer.classList.toggle('hidden', !e.target.checked);
    });


    document.querySelectorAll('#postTypeTabs a[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', event => {
            state.postCreation.type = event.target.dataset.postType;
            if (state.postCreation.type === 'poll') {
                renderPollOptionsUI();
            }
        });
    });

    document.getElementById('copyInviteLinkBtn').addEventListener('click', () => {
        const linkInput = document.getElementById('inviteLinkInput');
        const linkToCopy = linkInput.value;

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(linkToCopy).then(() => {
                showStatus('Invite link copied!', 'success');
            }).catch(err => {
                console.error('Failed to copy with Clipboard API:', err);
                showStatus('Could not copy link.', 'danger');
            });
        } else {
            linkInput.select();
            try {
                document.execCommand('copy');
                showStatus('Invite link copied!', 'success');
            } catch (err) {
                console.error('Fallback copy failed:', err);
                showStatus('Could not copy link.', 'danger');
            }
        }
    });

    document.getElementById('dashboardSortSelect').addEventListener('change', (e) => {
        state.dashboardFeed.sortBy = e.target.value;
        resetAndRenderDashboardFeed();
    });

    document.getElementById('dashboardTagFilter').addEventListener(
        'input',
        debounce(e => {
            state.dashboardFeed.filter.tags = e.target.value;
            resetAndRenderDashboardFeed();
        }, 500)
    );

    document.getElementById('youtubeSearchBtn').addEventListener('click',
        e => handleYouTubeSearch(e.currentTarget)
    );
    document.getElementById('youtubeSearchInput').addEventListener('keypress', e => {
        if (e.key === 'Enter') handleYouTubeSearch(document.getElementById('youtubeSearchBtn'));
    });

    document.getElementById('wishlistLinkInput').addEventListener('keypress', e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('addWishlistItemBtn').click();
        }
    });

    document.getElementById('imageFileInput').addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
            handleImageUpload(e.target.files[0]);
        }
    });

    document.body.addEventListener('change', e => {
        if (e.target.id === 'circleSortSelect') {
            state.circleView.sortBy = e.target.value;
            resetAndRenderCircleFeed(state.circleView.currentCircle._id);
        }
    });
    document.body.addEventListener('input', debounce(e => {
        if (e.target.id === 'circleTagFilter') {
            state.circleView.tags = e.target.value;
            resetAndRenderCircleFeed(state.circleView.currentCircle._id);
        }
    }, 500));

    document.getElementById('playlistPlayerModal')
        .addEventListener('hidden.bs.modal', () => {
            if (ytPlaylistPlayer && typeof ytPlaylistPlayer.destroy === 'function') {
                ytPlaylistPlayer.destroy();
                ytPlaylistPlayer = null;
            }
        });
    document.getElementById('playlist-prev-btn').addEventListener('click', () => {
        if (ytPlaylistPlayer) ytPlaylistPlayer.previousVideo();
    });
    document.getElementById('playlist-next-btn').addEventListener('click', () => {
        if (ytPlaylistPlayer) ytPlaylistPlayer.nextVideo();
    });
    document.getElementById('playlist-queue-list').addEventListener('click', (e) => {
        const item = e.target.closest('.playlist-queue-item');
        if (item && ytPlaylistPlayer) {
            const index = parseInt(item.dataset.index, 10);
            ytPlaylistPlayer.playVideoAt(index);
        }
    });

    window.addEventListener('hashchange', handleRoute);

    document.body.addEventListener('click', async e => {
        const link = e.target.closest('a');
        if (link && link.getAttribute('href') === '#') {
            e.preventDefault();
            if (link.classList.contains('btn') && !link.dataset.action) {
                window.location.hash = '';
            }
        }

        const target = e.target.closest('[data-action]');
        if (!target) return;
        const {
            action,
            ...data
        } = target.dataset;

        switch (action) {
            case 'filter-activity':
                state.activityCenter.filter = data.filter;
                loadActivityItems(true); // `true` forces a reset and reload
                break;

            case 'load-more-activity':
                loadActivityItems(false); // `false` fetches the next page
                break;

            case 'open-edit-post':
                handleOpenEditModal(data.postId, data.circleId);
                break;
            case 'save-post-edits':
                handleSavePostEdits(target);
                break;
            case 'edit-chat-participants':
                {
                    const {
                        circleId,
                        participant_ids
                    } = state.postEditing;
                    openChatParticipantSelector(circleId, 'edit', participant_ids);
                    break;
                }
            case 'open-chat':
                handleOpenChatModal(data.postId);
                break;
            case 'send-direct-invite':
                {
                    const modal = target.closest('#inviteCircleModal');
                    const circleId = modal.dataset.circleId;
                    const usernameInput = modal.querySelector('#directInviteUsernameInput');
                    const username = usernameInput.value.trim();
                    if (!username) {
                        showStatus('Please enter a username.', 'warning');
                        return;
                    }
                    setButtonLoading(target, true);
                    try {
                        await apiFetch(`/circles/${circleId}/invite-user`, {
                            method: 'POST',
                            body: JSON.stringify({
                                username
                            })
                        });
                        showStatus(`Invitation sent to ${username}!`, 'success');
                        usernameInput.value = '';
                    } catch (error) {
                        // apiFetch already shows error message
                    } finally {
                        setButtonLoading(target, false);
                    }
                    break;
                }
            case 'show-seen-status':
                handleShowSeenStatus(data.postId);
                break;
            case 'delete-post':
                handleDeletePost(data.postId, data.circleId);
                break;
            case 'filter-feed':
                state.dashboardFeed.filter.circle_id = data.circleId || null;
                renderMyCircles(state.myCircles);
                if (window.location.hash !== '') {
                    window.location.hash = '';
                } else {
                    resetAndRenderDashboardFeed();
                }
                break;
            case 'invite-to-circle':
                handleInviteToCircle(data.circleId);
                break;
            case 'open-yt-search':
                bootstrap.Modal.getOrCreateInstance(document.getElementById('youtubeSearchModal')).show();
                break;
            case 'open-comments':
                e.preventDefault();
                handleOpenCommentsModal(data.postId, data.postAuthorUsername);
                break;
            case 'view-comment-thread':
                handleViewCommentThread(data.postId, data.commenterId, data.commenterUsername);
                break;
            case 'delete-comment':
                if (confirm('Are you sure you want to delete this comment?')) {
                    try {
                        await apiFetch(`/comments/${data.commentId}`, {
                            method: 'DELETE'
                        });
                        target.closest('.comment-bubble') ?.remove();
                        const postCard = document.querySelector(`.post-card-wrapper[data-post-id="${data.postId}"]`);
                        const commentButton = postCard ?.querySelector(`[data-action="open-comments"]`);
                        if (commentButton) {
                            const textContent = commentButton.textContent || '';
                            const currentCount = parseInt(textContent.match(/\d+$/) ?.[0] || '0', 10);
                            commentButton.innerHTML = `<i class="bi bi-chat-left-text"></i> ${Math.max(0, currentCount - 1)}`;
                        }
                        showStatus('Comment deleted.', 'success');
                    } catch {
                        showStatus('Failed to delete comment.', 'danger');
                    }
                }
                break;
            case 'vote-poll':
                handlePollVote(data.postId, parseInt(data.optionIndex));
                break;
            case 'generate-poll-from-text':
                handleGeneratePollFromText(target);
                break;
            case 'add-poll-option':
                if (state.postCreation.pollData.options.length < 5) {
                    state.postCreation.pollData.options.push('');
                    renderPollOptionsUI();
                }
                break;
            case 'remove-poll-option':
                if (state.postCreation.pollData.options.length > 2) {
                    state.postCreation.pollData.options.splice(data.index, 1);
                    renderPollOptionsUI();
                }
                break;
            case 'open-manage-circle':
                handleOpenManageCircle(data.circleId);
                break;
            case 'manage-member-role':
                handleManageMemberRole(target, data.userId, data.newRole);
                break;
            case 'manage-member-kick':
                handleKickMember(target, data.userId, data.username);
                break;
            case 'accept-invite':
                {
                    setButtonLoading(target, true);
                    try {
                        await apiFetch(`/invitations/${data.inviteId}/accept`, {
                            method: 'POST'
                        });
                        showStatus('Invitation accepted!', 'success');
                        await Promise.all([openNotificationsModal(), activityPoller.poll(), fetchAndRenderAll()]);
                    } catch (error) {
                        console.error('Failed to accept invitation:', error);
                    } finally {
                        setButtonLoading(target, false);
                    }
                    break;
                }
            case 'reject-invite':
                {
                    setButtonLoading(target, true);
                    try {
                        await apiFetch(`/invitations/${data.inviteId}/reject`, {
                            method: 'POST'
                        });
                        showStatus('Invitation declined.', 'info');
                        await Promise.all([openNotificationsModal(), activityPoller.poll()]);
                    } catch (e) {
                        showStatus(e.message, 'danger');
                    } finally {
                        setButtonLoading(target, false);
                    }
                    break;
                }
            case 'mark-notification-read':
                {
                    target.closest('.notification-card').style.opacity = '0.5';
                    try {
                        await apiFetch(`/notifications/${data.notificationId}/read`, {
                            method: 'POST'
                        });
                        await Promise.all([openNotificationsModal(), activityPoller.poll()]);
                    } catch (e) {
                        showStatus('Could not mark as read.', 'danger');
                    }
                    break;
                }
            case 'mark-all-read':
                {
                    setButtonLoading(target, true);
                    try {
                        await apiFetch(`/users/me/notifications/read-all`, {
                            method: 'POST'
                        });
                        await Promise.all([openNotificationsModal(), activityPoller.poll()]);
                    } catch (e) {
                        showStatus('Could not mark all as read.', 'danger');
                    } finally {
                        setButtonLoading(target, false);
                    }
                    break;
                }
            case 'filter-by-tag':
                if (!dom.circleView.classList.contains('hidden')) {
                    const filterInput = document.getElementById('circleTagFilter');
                    if (filterInput) {
                        filterInput.value = data.tag;
                        state.circleView.tags = data.tag;
                        resetAndRenderCircleFeed(state.circleView.currentCircle._id);
                    }
                } else {
                    const filterInput = document.getElementById('dashboardTagFilter');
                    if (filterInput) {
                        filterInput.value = data.tag;
                        state.dashboardFeed.filter.tags = data.tag;
                        resetAndRenderDashboardFeed();
                    }
                }
                break;
            case 'play-playlist':
                try {
                    const playlistDataString = data.playlist.replace(/'/g, "'").replace(/"/g, '"');
                    const playlist = JSON.parse(playlistDataString);
                    openPlaylistPlayerModal(playlist);
                } catch (err) {
                    console.error("Failed to parse playlist data:", err);
                    showStatus("Could not play the playlist.", "danger");
                }
                break;
            case 'submit-post':
                handleCreatePost(target);
                break;
            case 'confirm-chat-participants':
                {
                    const modal = target.closest('#chatParticipantSelectorModal');
                    const selectedIds = Array.from(modal.querySelectorAll('#chatParticipantList input:checked')).map(input => input.value);
                    bootstrap.Modal.getInstance(modal).hide();

                    const context = target.dataset.context || 'create';
                    if (context === 'create') {
                        state.postCreation.chat.participant_ids = selectedIds;
                        await finalizePostCreation();
                    } else { // context === 'edit'
                        state.postEditing.participant_ids = selectedIds;
                    }
                    break;
                }
            case 'add-video-to-playlist':
                {
                    const video = JSON.parse(data.video.replace(/'/g, "'"));
                    const activeModal = document.querySelector('.modal.show'); // Find the currently open modal
                    if (!activeModal) break;

                    const container = activeModal.querySelector('.selectedPlaylistVideosContainer');
                    if (!container) break;

                    const currentVideos = JSON.parse(container.dataset.videos || '[]');
                    const newVideos = [...currentVideos, video];

                    renderSelectedPlaylistVideos(container, newVideos);

                    if (activeModal.id === 'createPostModal') {
                        state.postCreation.playlist.videos = newVideos;
                    }

                    target.textContent = 'Added';
                    target.disabled = true;
                    target.classList.remove('btn-primary');
                    target.classList.add('btn-success');
                    break;
                }
            case 'remove-video-from-playlist':
                {
                    const videoId = data.videoId;
                    const container = target.closest('.selectedPlaylistVideosContainer');
                    if (!container) break;

                    const currentVideos = JSON.parse(container.dataset.videos || '[]');
                    const newVideos = currentVideos.filter(v => v.id !== videoId);

                    renderSelectedPlaylistVideos(container, newVideos);

                    const activeModal = container.closest('.modal');
                    if (activeModal && activeModal.id === 'createPostModal') {
                        state.postCreation.playlist.videos = newVideos;
                        const searchResultsContainer = document.getElementById('youtubeSearchResultsContainer');
                        const correspondingAddButton = searchResultsContainer.querySelector(`[data-video*='"id":"${videoId}"']`);
                        if (correspondingAddButton) {
                            correspondingAddButton.innerHTML = '<i class="bi bi-plus-lg"></i>';
                            correspondingAddButton.disabled = false;
                            correspondingAddButton.classList.add('btn-primary');
                            correspondingAddButton.classList.remove('btn-success');
                        }
                    }
                    break;
                }
            case 'add-wishlist-item':
                {
                    const input = document.getElementById('wishlistLinkInput');
                    const url = input.value.trim();
                    if (url) {
                        try {
                            new URL(url);
                            if (state.postCreation.wishlist.urls.includes(url)) {
                                showStatus('This link has already been added.', 'info');
                                return;
                            }
                            state.postCreation.wishlist.urls.push(url);
                            renderWishlistStagingArea();
                            input.value = '';
                        } catch {
                            showStatus('Please enter a valid URL.', 'warning');
                        }
                    }
                    break;
                }
            case 'remove-wishlist-item':
                {
                    const item = target.closest('.list-group-item');
                    const index = parseInt(item.dataset.index, 10);
                    state.postCreation.wishlist.urls.splice(index, 1);
                    renderWishlistStagingArea();
                    break;
                }
            case 'edit-wishlist-item':
                {
                    const item = target.closest('.list-group-item');
                    item.querySelector('.url-text').classList.add('hidden');
                    item.querySelector('.url-input').classList.remove('hidden');
                    target.classList.add('hidden');
                    item.querySelector('[data-action="save-wishlist-item"]').classList.remove('hidden');
                    item.querySelector('.url-input').focus();
                    break;
                }
            case 'save-wishlist-item':
                {
                    const item = target.closest('.list-group-item');
                    const input = item.querySelector('.url-input');
                    const newUrl = input.value.trim();
                    const index = parseInt(item.dataset.index, 10);
                    try {
                        new URL(newUrl);
                        state.postCreation.wishlist.urls[index] = newUrl;
                        renderWishlistStagingArea();
                    } catch {
                        showStatus('Please enter a valid URL.', 'warning');
                    }
                    break;
                }
            case 'add-yt-video-from-url':
                addYoutubeVideoFromUrl(target);
                break;
            case 'edit-add-wishlist-item':
                {
                    const container = document.getElementById('editWishlistItemsContainer');
                    const new_item_html = `
                          <div class="input-group input-group-sm mb-2">
                            <input type="url" class="form-control edit-wishlist-item-input" value="" placeholder="https://...">
                            <button class="btn btn-outline-danger" type="button" data-action="edit-remove-wishlist-item"><i class="bi bi-trash"></i></button>
                          </div>
                    `;
                    container.insertAdjacentHTML('beforeend', new_item_html);
                    container.lastElementChild.querySelector('input').focus();
                    break;
                }
            case 'edit-remove-wishlist-item':
                {
                    target.closest('.input-group').remove();
                    break;
                }
        }
    });

    document.addEventListener('dragend', (e) => {
        if (e.target.classList.contains('yt-selected-video')) {
            draggedItem.classList.remove('dragging');
            draggedItem = null;

            const container = e.target.closest('.selectedPlaylistVideosContainer');
            if (!container) return;

            setTimeout(() => {
                const videoElements = [...container.querySelectorAll('.yt-selected-video')];
                const currentVideos = JSON.parse(container.dataset.videos || '[]');

                // Reorder the actual data array based on the new DOM order
                const newVideosOrder = videoElements
                    .map(el => currentVideos.find(v => v.id === el.dataset.videoId))
                    .filter(Boolean); // filter(Boolean) removes any undefined if something went wrong

                // Update the data attribute with the new order
                container.dataset.videos = JSON.stringify(newVideosOrder);

                // If in create modal, sync global state
                const activeModal = container.closest('.modal');
                if (activeModal && activeModal.id === 'createPostModal') {
                    state.postCreation.playlist.videos = newVideosOrder;
                }
            }, 0);
        }
    });

    const saveCircleSettingsBtn = document.getElementById('saveCircleSettingsBtn');

    saveCircleSettingsBtn.addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        const circleId = document.getElementById('manageCircleId').value;
        const name = document.getElementById('manageCircleName').value;
        const description = document.getElementById('manageCircleDescription').value;
        const isPublic = document.getElementById('manageCircleIsPublic').checked;

        if (!name) {
            showStatus('Circle name cannot be empty.', 'danger');
            return;
        }

        const payload = {
            name,
            description,
            is_public: isPublic
        };

        setButtonLoading(btn, true);
        try {
            const updatedCircle = await apiFetch(`/circles/${circleId}`, {
                method: 'PATCH',
                body: JSON.stringify(payload)
            });

            const manageModal = bootstrap.Modal.getInstance(document.getElementById('manageCircleModal'));
            manageModal.hide();
            showStatus('Circle settings saved successfully!', 'success');

            if (state.circleView.currentCircle ?._id === circleId) {
                await resetAndRenderCircleFeed(circleId);
            }
            await renderAllSidebarComponents();

        } catch (error) {
            console.error('Failed to save circle settings:', error);
        } finally {
            setButtonLoading(btn, false);
        }
    });

    document.getElementById('deleteCircleConfirmationInput')
        .addEventListener('input', (e) => {
            const circleName = document.getElementById('confirmDeleteCircleName').textContent;
            document.getElementById('deleteCircleBtn').disabled = e.target.value !== circleName;
        });
    document.getElementById('deleteCircleBtn')
        .addEventListener('click', (e) => handleDeleteCircle(e.currentTarget));

    function renderPollOptionsUI() {
        const container = document.getElementById('pollOptionsContainer');
        const questionInput = document.getElementById('pollQuestionInput');
        if (!container || !questionInput) return;

        const {
            question,
            options
        } = state.postCreation.pollData;
        questionInput.value = question;

        container.innerHTML = options.map((optionText, index) => `
<div class="input-group input-group-sm mb-2">
<span class="input-group-text">${index + 1}</span>
<input type="text" class="form-control poll-option-input"
data-index="${index}"
value="${optionText}"
placeholder="Option ${index + 1}">
<button class="btn btn-outline-danger"
type="button"
data-action="remove-poll-option"
data-index="${index}"
${options.length <= 2 ? 'disabled' : ''}>
<i class="bi bi-trash"></i>
</button>
</div>
`).join('');

        const addBtn = document.getElementById('addPollOptionBtn');
        if (addBtn) {
            addBtn.classList.toggle('hidden', options.length >= 5);
        }
    }

    async function handleGeneratePollFromText(btn) {
        const input = document.getElementById('poll-ai-prompt');
        const text = input.value.trim();

        if (text.length < 10) {
            return showStatus('Please provide a more detailed description for your poll.', 'warning');
        }

        setButtonLoading(btn, true);
        try {
            const data = await apiFetch('/utils/generate-poll-from-text', {
                method: 'POST',
                body: JSON.stringify({
                    text
                })
            });
            state.postCreation.pollData.question = data.question;
            state.postCreation.pollData.options = data.options
                .slice(0, 5)
                .map(opt => opt.text);
            renderPollOptionsUI();
        } catch (error) {
            showStatus('Could not generate poll from text. Please try rephrasing.', 'danger');
        } finally {
            setButtonLoading(btn, false);
        }
    }

    initTheme();
    handleRoute();
});
