class YouTubeMiniApp {
	constructor() {
		// Example placeholder endpoint. Replace with your own or a serverless function.
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
			bounce: false,
		},
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
		},
	},
	retina_detect: true,
	background: {
		color: "transparent"
	},
};
const particlesConfigLight = {
	particles: {
		number: {
			value: 70,
			density: {
				enable: true,
				value_area: 800
			}
		},
		color: {
			value: ["#007bff", "#6f42c1", "#1a1334"]
		},
		shape: {
			type: "circle"
		},
		opacity: {
			value: {
				min: 0.2,
				max: 0.6
			},
			animation: {
				enable: true,
				speed: 1,
				minimumValue: 0.2,
				sync: false
			}
		},
		size: {
			value: {
				min: 1,
				max: 3
			}
		},
		line_linked: {
			enable: false
		},
		move: {
			enable: true,
			speed: 0.8,
			direction: "none",
			random: true,
			straight: false,
			out_mode: "out",
			bounce: false,
		},
	},
	interactivity: {
		events: {
			onhover: {
				enable: true,
				mode: "bubble"
			},
			onclick: {
				enable: false
			},
			resize: true
		},
		modes: {
			bubble: {
				distance: 200,
				size: 4,
				duration: 2,
				opacity: 0.8
			},
		},
	},
	retina_detect: true,
	background: {
		color: "transparent"
	},
};

const updateThemeIcons = (theme) => {
	const themeToggleBtns = [
		document.getElementById('themeToggleBtn'),
		document.getElementById('themeToggleBtnLogin')
	];
	const iconHtml = theme === 'light' ? '<i class="bi bi-moon-stars-fill"></i>' : '<i class="bi bi-sun-fill"></i>';
	themeToggleBtns.forEach(btn => {
		if (btn) btn.innerHTML = iconHtml;
	});
};

const initTheme = () => {
	const savedTheme = localStorage.getItem('theme') ||
		(window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
	document.documentElement.setAttribute('data-theme', savedTheme);
	updateThemeIcons(savedTheme);
	tsParticles.load('particles-js', savedTheme === 'light' ? particlesConfigLight : particlesConfigDark);
};

const toggleTheme = () => {
	const currentTheme = document.documentElement.getAttribute('data-theme');
	const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
	document.documentElement.setAttribute('data-theme', newTheme);
	localStorage.setItem('theme', newTheme);
	updateThemeIcons(newTheme);
	tsParticles.load('particles-js', newTheme === 'light' ? particlesConfigLight : particlesConfigDark);
};

const BASE_URL = 'http://localhost:8000';

const state = {
	accessToken: localStorage.getItem('accessToken') || null,
	refreshToken: localStorage.getItem('refreshToken') || null,
	currentUser: null,
	myCircles: [],
	dashboardFeed: {
		filter: {
			circle_id: null,
			tags: ''
		},
		sortBy: 'newest',
		skip: 0,
		limit: 10,
		hasMore: true,
		isLoading: false
	},
	circleView: {
		currentCircle: null,
		sortBy: 'newest',
		tags: '',
		skip: 0,
		limit: 10,
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
			options: ['', ''] // Start with two empty options
		},
		wishlist: {
			urls: []
		}
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
	const id = `a${Date.now()}`;
	document.getElementById('globalStatus').innerHTML = `
<div id="${id}" class="alert alert-${type} alert-dismissible fade show">
${msg}
<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
`;
	setTimeout(() => {
		const alertEl = document.getElementById(id);
		if (alertEl) bootstrap.Alert.getOrCreateInstance(alertEl)?.close();
	}, 4000);
};

const getYouTubeID = (url) => {
	const arr = url.match(/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/);
	return (arr && arr[1]) ? arr[1] : null;
};

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
				}),
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
		let err = {};
		try {
			err = await response.json();
		} catch {}
		const detail = err.detail || `Error: ${response.status}`;
		if (response.status !== 403 && response.status !== 401) {
			showStatus(detail, 'danger');
		}
		throw new Error(detail);
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
	state.accessToken = null;
	state.refreshToken = null;
	state.currentUser = null;
	localStorage.removeItem('accessToken');
	localStorage.removeItem('refreshToken');
	localStorage.removeItem('pendingInviteToken');
	window.location.hash = '';
	handleRoute();
};

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
	renderAllSidebarComponents();
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

async function handleRoute() {
	await fetchCurrentUser();
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
	renderAllSidebarComponents();
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
	let html = `
<a href="#" class="list-group-item clickable list-group-item-action ${!circle_id ? 'active' : ''}"
data-action="filter-feed" data-circle-id="">
<i class="bi bi-collection-fill me-2"></i>All My Circles
</a>`;
	html += circles.map(c => `
<div class="list-group-item d-flex justify-content-between align-items-center p-0">
<a href="#/circle/${c._id}" class="flex-grow-1 list-group-item-action border-0 clickable px-3 py-2"
data-action="view-circle" data-circle-id="${c._id}" data-bs-toggle="tooltip" title="${c.name}">
<i class="bi bi-hash"></i> ${c.name} ${c.is_password_protected ? '<i class="bi bi-lock-fill small ms-1 text-muted"></i>' : ''}
</a>
</div>
`).join('');
	dom.myCirclesContainer.innerHTML = html || `<div class="empty-placeholder small">No circles yet.</div>`;
	initTooltips();
}

async function resetAndRenderDashboardFeed() {
	state.dashboardFeed.skip = 0;
	state.dashboardFeed.hasMore = true;
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

async function resetAndRenderCircleFeed(circleId) {
	state.circleView.skip = 0;
	state.circleView.hasMore = true;
	dom.circleFeedContainer.innerHTML = '';
	dom.circleHeader.innerHTML = '';
	await renderCircleFeed(circleId);
}

function renderJoinCirclePrompt(circleId, circleName) {
	if (!state.currentUser) {
		dom.circleHeader.innerHTML = `<h2><i class="bi bi-lock-fill"></i> ${circleName}</h2>`;
		dom.circleFeedContainer.innerHTML = `
<div class="empty-placeholder">
This is a private, password-protected circle. Please <a href="#" id="loginFromCircleView">log in</a> to join.
</div>`;
		document.getElementById('loginFromCircleView').addEventListener('click', (e) => {
			e.preventDefault();
			window.location.hash = '';
			handleRoute();
		});
		return;
	}
	dom.circleHeader.innerHTML = `
<div class="d-flex justify-content-between align-items-center">
<h2><i class="bi bi-lock-fill"></i> Join ${circleName}</h2>
<a href="#" class="btn btn-secondary btn-sm"><i class="bi bi-arrow-left"></i> Back to Feed</a>
</div>`;
	dom.circleFeedContainer.innerHTML = `
<div class="glass-card text-center">
<p class="fs-5">This circle is protected. Enter the password to gain access.</p>
<div class="input-group mt-3 mx-auto" style="max-width: 300px;">
<input type="password" id="joinCirclePasswordInput" class="form-control" placeholder="Enter Password...">
<button class="btn btn-primary" id="joinCircleSubmitBtn" data-circle-id="${circleId}">Join</button>
</div>
</div>`;
}

async function renderCircleFeed(circleId) {
	const feedState = state.circleView;
	if (!feedState.hasMore || feedState.isLoading) return;
	feedState.isLoading = true;
	dom.feedLoader.classList.remove('hidden');

	try {
		if (feedState.skip === 0) {
			const circleDetails = await apiFetch(`/circles/${circleId}`);
			feedState.currentCircle = circleDetails;
			const userRole = circleDetails.user_role;
			let managementControlsHtml = '';
			if (userRole === 'admin' || userRole === 'moderator') {
				managementControlsHtml = `<button class="btn btn-sm btn-secondary" data-action="open-manage-circle" data-circle-id="${circleDetails._id}"><i class="bi bi-gear-fill"></i> Manage Circle</button>`;
			}

			dom.circleHeader.innerHTML = `
<div class="d-flex justify-content-between align-items-center flex-wrap gap-3">
<div>
<h2><i class="bi bi-hash"></i> ${circleDetails.name}</h2>
<p class="text-muted mb-0">${circleDetails.description || 'A shared space for posts.'}</p>
</div>
<div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">
<a href="#" class="btn btn-secondary btn-sm"><i class="bi bi-arrow-left"></i> Back</a>
<div class="input-group input-group-sm" style="width: auto;">
<span class="input-group-text bg-transparent border-end-0" style="border-color: var(--border-color);"><i class="bi bi-tags"></i></span>
<input type="text" id="circleTagFilter" class="form-control border-start-0" placeholder="Filter by tags..." value="${feedState.tags}" style="min-width: 150px;">
</div>
<select id="circleSortSelect" class="form-select form-select-sm" style="width: auto;">
<option value="newest" ${feedState.sortBy === 'newest' ? 'selected' : ''}>Sort: Newest</option>
</select>
<div class="btn-group">
<button class="btn btn-sm btn-primary" data-action="open-chat" data-circle-id="${circleId}"><i class="bi bi-chat-dots-fill"></i> Chat</button>
<button class="btn btn-sm btn-success" data-action="invite-to-circle" data-circle-id="${circleId}"><i class="bi bi-send"></i> Invite</button>
${managementControlsHtml}
</div>
<button id="togglePostCreatorCircleBtn" class="btn btn-sm btn-primary ms-2">
<i class="bi bi-pencil-square"></i> New Post
</button>
</div>
</div>
`;
		}

		let url = `/circles/${circleId}/feed?skip=${feedState.skip}&limit=${feedState.limit}&sort_by=${feedState.sortBy}`;
		if (feedState.tags) {
			url += `&tags=${encodeURIComponent(feedState.tags)}`;
		}
		const feedData = await apiFetch(url);
		appendPosts(feedData.posts, dom.circleFeedContainer, feedState.currentCircle.name);
		feedState.hasMore = feedData.has_more;
		feedState.skip += feedData.posts.length;

		if (!dom.circleFeedContainer.querySelector('.post-card-wrapper') && !feedData.has_more) {
			dom.circleFeedContainer.insertAdjacentHTML('beforeend', `<div class="empty-placeholder">This circle has no posts yet. Be the first!</div>`);
		}
	} catch (error) {
		try {
			const statusData = await apiFetch(`/circles/${circleId}/status`);
			if (statusData.is_password_protected) {
				renderJoinCirclePrompt(circleId, statusData.name);
			} else {
				dom.circleHeader.innerHTML = '';
				dom.circleFeedContainer.innerHTML = `<div class="empty-placeholder text-danger">This circle is private and you are not a member.</div>`;
			}
		} catch (statusError) {
			dom.circleHeader.innerHTML = '';
			dom.circleFeedContainer.innerHTML = `<div class="empty-placeholder text-danger">Could not find or access this circle.</div>`;
		}
	} finally {
		feedState.isLoading = false;
		dom.feedLoader.classList.add('hidden');
	}
}

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
	const canModify = (post) => state.currentUser && post.author_username === state.currentUser.username;
	const canPin = () => state.circleView.currentCircle && ['admin', 'moderator'].includes(state.circleView.currentCircle.user_role);

	const postsHtml = posts.filter(post => post && (post.id || post._id)).map(post => {
		let contentHtml = '';
		const postType = post.content.post_type || 'standard';
		const postId = post.id || post._id;

		switch (postType) {
			case 'yt-playlist':
				{
					const playlist = post.content.playlist_data;
					const coverImage = playlist.videos.length > 0 ? playlist.videos[0].imageSrc : 'https://via.placeholder.com/400x225.png?text=Playlist';
					const playlistDataString = JSON.stringify(playlist).replace(/'/g, "&apos;").replace(/"/g, "&quot;");
					contentHtml = `
<div class="card mt-3 playlist-card" style="background-color: var(--form-input-bg); border-color: var(--border-color); position: relative;">
<img src="${coverImage}" class="card-img-top" alt="Playlist Cover">
<div class="card-body">
<h5 class="card-title mb-1">${playlist.name}</h5>
<p class="card-text text-muted small">${playlist.videos.length} videos</p>
</div>
<div class="playlist-play-overlay" data-action="play-playlist" data-playlist='${playlistDataString}'>
<i class="bi bi-play-circle-fill"></i><span>Play All</span>
</div>
</div>`;
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
						const voteAction = isPollActive ? `data-action="vote-poll" data-post-id="${postId}" data-option-index="${index}"` : '';

						return `
<div class="poll-option ${isVotedByUser ? 'voted-by-user' : ''} ${!isPollActive ? 'poll-disabled' : ''}" ${voteAction}>
    <div class="progress" style="width: ${percentage}%;"></div>
    <div class="d-flex justify-content-between align-items-center position-relative">
        <span>${option.text} ${isVotedByUser ? '<i class="bi bi-check-circle-fill"></i>' : ''}</span>
        <span class="fw-bold small">${percentage.toFixed(0)}% (${option.votes})</span>
    </div>
</div>`;
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
							pollFooterHtml = `<small class="text-muted">Total votes: ${totalVotes} &bull; <i class="bi bi-clock"></i> ${timeRemaining}</small>`;
						} else {
							pollFooterHtml = `<small class="text-muted"><strong><i class="bi bi-lock-fill"></i> Poll closed on ${expiresDate.toLocaleDateString()}</strong> &bull; ${totalVotes} votes</small>`;
						}
					} else {
						pollFooterHtml = `<small class="text-muted">Total votes: ${totalVotes}</small>`;
					}

					contentHtml = `
<h5 class="card-title">${poll.question}</h5>
<div class="poll-container">${pollOptionsHtml}</div>
${pollFooterHtml}`;
					break;
				}
			case 'wishlist':
				{
					const rawWishlistData = post.content.wishlist_data;
					const wishlistItems = Array.isArray(rawWishlistData) ?
						rawWishlistData :
						(rawWishlistData ? [rawWishlistData] : []);

					if (post.content.text) {
						contentHtml += `<h5 class="card-title">${post.content.text}</h5>`;
					}
					contentHtml += '<div class="list-group list-group-flush mt-3">';
					wishlistItems.forEach(item => {
						if (item && item.url) {
							let hostDomain = 'link';
							try {
								hostDomain = item.title || (new URL(item.url).hostname.replace('www.', ''));
							} catch (e) {
								console.error(`Invalid URL in wishlist post ${postId}: ${item.url}`);
							}
							contentHtml += `
                                <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="list-group-item list-group-item-action d-flex align-items-center">
                                    <img src="https://www.google.com/s2/favicons?domain=${hostDomain}&sz=32" class="favicon me-2" alt="${hostDomain} favicon">
                                    <span class="text-truncate">${item.url}</span>
                                    <i class="bi bi-box-arrow-up-right ms-auto text-muted"></i>
                                </a>`;
						}
					});
					contentHtml += '</div>';
					break;
				}
			case 'image':
				{
					const img = post.content.image_data;
					if (img && img.url) {
						contentHtml = `
<div class="card mt-3" style="background-color: var(--form-input-bg); border-color: var(--border-color);">
<img src="${img.url}" class="card-img-top" alt="User's posted image">
</div>
`;
					} else {
						contentHtml = `<p class="text-muted">No image data found.</p>`;
					}
					break;
				}
			default:
				{
					if (post.content.text) {
						contentHtml += `<p class="card-text" style="white-space: pre-wrap;">${post.content.text}</p>`;
					}
					if (post.content.link) {
						const videoId = getYouTubeID(post.content.link);
						if (videoId) {
							contentHtml += `
<div class="video-container my-2">
<iframe src="https://www.youtube.com/embed/${videoId}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
</div>`;
						} else {
							try {
								const host = new URL(post.content.link).hostname;
								contentHtml += `
<a href="${post.content.link}" target="_blank" rel="noopener noreferrer" class="link-preview d-block text-decoration-none">
<strong class="link-preview-title d-block">${post.content.link}</strong>
<span class="link-preview-host">${host}</span>
</a>`;
							} catch (e) {
								contentHtml += `<p class="text-muted">Invalid link: ${post.content.link}</p>`;
							}
						}
					}
					break;
				}
		}

		if (post.content.tags && post.content.tags.length > 0) {
			contentHtml += `
<div class="mt-3 post-tags">
${post.content.tags.map(tag => `<span class="badge rounded-pill bg-secondary me-1" data-action="filter-by-tag" data-tag="${tag}">${tag}</span>`).join(' ')}
</div>`;
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

		const seenByFooter = `
<div class="post-footer mt-3 pt-3">
    <div class="seen-by-container ${post.is_seen_by_user ? 'seen-by-user' : ''}"
        data-action="show-seen-status"
        data-post-id="${postId}"
        data-seen-count="${seenCount}"
        title="See who has viewed this post">
        <div class="avatar-stack">
            ${seenByUsers.map(user => `<img src="${generateAvatarUrl(user.username)}" class="avatar-small" title="${user.username}">`).join('')}
        </div>
        <span class="seen-by-text">${seenByText}</span>
    </div>
</div>
`;


		const displayCircleName = circleName || post.circle_name;
		const dropdownMenu = `
<div class="dropdown">
<button class="btn btn-sm py-0 px-2" type="button" data-bs-toggle="dropdown" data-bs-toggle="tooltip" title="More options"><i class="bi bi-three-dots-vertical"></i></button>
<ul class="dropdown-menu dropdown-menu-dark">
${canPin() ? `<li><a class="dropdown-item" href="#" data-action="pin-post" data-post-id="${postId}">${post.is_pinned ? 'Unpin Post' : 'Pin Post'}</a></li>` : ''}
${canModify(post) ? `<li><a class="dropdown-item text-danger" href="#" data-action="delete-post" data-post-id="${postId}" data-circle-id="${post.circle_id}">Delete Post</a></li>` : ''}
</ul>
</div>`;

		return `
<div class="post-card-wrapper" data-post-id="${postId}" data-post-wrapper-id="${postId}">
<div class="glass-card post-card">
<div class="post-card-body">
<div class="d-flex justify-content-between align-items-start">
<div class="d-flex align-items-center">
    <img src="${generateAvatarUrl(post.author_username)}" class="avatar me-3">
<div>
<strong class="d-block">${post.author_username} ${post.is_pinned ? '<i class="bi bi-pin-angle-fill text-primary" title="Pinned Post"></i>' : ''}</strong>
<small class="text-muted">in <a href="#/circle/${post.circle_id}" class="text-reset fw-bold">${displayCircleName}</a> &bull; ${new Date(post.created_at).toLocaleString()}</small>
</div>
</div>
${(canPin() || canModify(post)) ? dropdownMenu : ''}
</div>
<div class="mt-3">${contentHtml}</div>
    ${seenByFooter}
</div>
</div>
</div>`;
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

const switchAuthView = (hideEl, showEl) => {
	hideEl.classList.add('animate-out');
	hideEl.addEventListener('animationend', () => {
		hideEl.classList.add('hidden');
		hideEl.classList.remove('animate-out');
		showEl.classList.remove('hidden');
		showEl.classList.add('animate-in');
		showEl.addEventListener('animationend', () => {
			showEl.classList.remove('animate-in');
			// UX Improvement: Auto-focus the first input field for a smoother login/register experience.
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
	} catch (error) {} finally {
		setButtonLoading(btn, false);
	}
}

async function handleCreateCircle() {
	const btn = document.getElementById('submitCircleButton');
	const name = document.getElementById('circleName').value;
	const description = document.getElementById('circleDescription').value;
	const is_public = document.getElementById('isPublicSwitch').checked;
	const passwordSwitch = document.getElementById('protectWithPasswordSwitch');
	const password = document.getElementById('circlePassword').value;
	const payload = {
		name,
		description,
		is_public
	};

	if (passwordSwitch.checked && password) {
		payload.password = password;
	} else if (passwordSwitch.checked && !password) {
		return showStatus('Password cannot be empty if protection is enabled.', 'warning');
	}

	setButtonLoading(btn, true);
	try {
		// UX Improvement: Capture the new circle data to navigate directly to it.
		const newCircle = await apiFetch('/circles', {
			method: 'POST',
			body: JSON.stringify(payload)
		});
		showStatus(`Circle "${newCircle.name}" created! Navigating...`, 'success');
		bootstrap.Modal.getInstance('#createCircleModal').hide();
		document.getElementById('createCircleForm').reset();
		document.getElementById('circlePasswordContainer').classList.add('hidden');

		// Update state locally instead of a full refetch for better performance.
		state.myCircles.push(newCircle);
		state.myCircles.sort((a, b) => a.name.localeCompare(b.name));
		renderMyCircles(state.myCircles);

		// Navigate to the new circle for a seamless user flow.
		window.location.hash = `#/circle/${newCircle._id}`;

	} catch (error) {
		// Error is already shown by apiFetch
	} finally {
		setButtonLoading(btn, false);
	}
}

async function handleImageUpload(file) {
	const previewContainer = document.getElementById('imageUploadPreviewContainer');
	const previewImg = document.getElementById('imageUploadPreview');
	const progressBar = document.getElementById('imageUploadProgressBar');

	previewImg.src = URL.createObjectURL(file);
	previewContainer.classList.remove('hidden');
	// UX Improvement: Reset progress bar state on new upload
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
				// UX Improvement: Show success color on the progress bar.
				progressBar.classList.add('bg-success');
			} else {
				showStatus(`Image upload failed: ${JSON.parse(xhr.responseText).error.message}`, 'danger');
				// UX Improvement: Show error color on the progress bar.
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

async function handleCreatePost(btn) {
	const creator = btn.closest('.modal-content, .post-creator');
	if (!creator) {
		showStatus('Could not find post creation form.', 'danger');
		return;
	}
	let circle_id;
	const hiddenInput = creator.querySelector('.circleIdInput');
	const select = creator.querySelector('.circleSelect');
	if (hiddenInput) {
		circle_id = hiddenInput.value;
	} else if (select) {
		circle_id = select.value;
	}
	if (!circle_id) {
		showStatus('You must select a circle to post in.', 'warning');
		return;
	}

	const postType = state.postCreation.type;
	const tags = creator.querySelector('.postTags').value.split(',').map(t => t.trim()).filter(Boolean);
	let payload = {
		tags
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
					payload.wishlist_data = urls.map(url => {
						let hostname = 'link';
						try {
							hostname = new URL(url).hostname;
						} catch {}
						return {
							url: url,
							title: hostname
						};
					});
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
					const options = state.postCreation.pollData.options
						.map(opt => opt.trim())
						.filter(Boolean);

					if (!question) {
						throw new Error('Please enter a poll question.');
					}
					if (options.length < 2) {
						throw new Error('Please provide at least two poll options.');
					}

					const durationHours = parseInt(creator.querySelector('#pollDurationSelect').value, 10);
					if (!durationHours || durationHours <= 0) {
						throw new Error('Please select a valid poll duration.');
					}

					payload.poll_data = {
						question: question,
						options: options.map(opt => ({
							text: opt
						}))
					};
					payload.poll_duration_hours = durationHours;
					break;
				}
			case 'image':
				{
					postTypeForApi = 'image';
					if (state.postCreation.imageData && state.postCreation.imageData.url) {
						payload.image_data = state.postCreation.imageData;
					} else {
						const urlInput = creator.querySelector('.imageUrlInput');
						const imageUrl = urlInput.value.trim();
						if (!imageUrl) throw new Error('Please upload an image or provide a valid image URL.');
						payload.link = imageUrl;
					}
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
		const createPostModal = bootstrap.Modal.getInstance('#createPostModal');
		if (createPostModal) {
			createPostModal.hide();
		}
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

async function handleDeletePost(postId, circleId) {
	// UX Improvement: A custom modal would be a better user experience than a browser confirm().
	// This would require adding new HTML which is out of scope, so we use confirm() for now.
	if (!confirm('Are you sure you want to permanently delete this post?')) return;
	try {
		await apiFetch(`/circles/${circleId}/posts/${postId}`, {
			method: 'DELETE'
		});
		showStatus('Post deleted.', 'success');
		if (state.circleView.currentCircle) {
			await resetAndRenderCircleFeed(state.circleView.currentCircle._id);
		} else {
			await resetAndRenderDashboardFeed();
		}
	} catch (error) {}
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
			if (users.length === 0) return '<li class="list-group-item text-muted">None</li>';
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

async function handleJoinCircle(circleId) {
	const btn = document.getElementById('joinCircleSubmitBtn');
	const passwordInput = document.getElementById('joinCirclePasswordInput');
	const password = passwordInput.value;
	if (!password) return showStatus('A password is required to join.', 'warning');

	setButtonLoading(btn, true);
	try {
		await apiFetch(`/circles/${circleId}/join`, {
			method: 'POST',
			body: JSON.stringify({
				password
			})
		});
		showStatus('Password accepted! You have joined the circle.', 'success');
		await fetchAndRenderAll();
		await resetAndRenderCircleFeed(circleId);
	} catch (error) {
		showStatus('Incorrect password or unable to join.', 'danger');
		passwordInput.value = '';
	} finally {
		setButtonLoading(btn, false);
	}
}

async function handleInviteToCircle(circleId) {
	const inviteModal = bootstrap.Modal.getOrCreateInstance('#inviteCircleModal');
	const qrContainer = document.getElementById('qrCodeContainer');
	const linkInput = document.getElementById('inviteLinkInput');
	qrContainer.innerHTML = `<div class="spinner-border text-primary" role="status"></div>`;
	linkInput.value = '';
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
		showStatus(error.message || 'This invite link is invalid or has expired.', 'danger');
		if (!isRedirect) window.location.hash = '';
	}
}

async function handlePinPost(postId) {
	try {
		const result = await apiFetch(`/posts/${postId}/pin`, {
			method: 'POST'
		});
		showStatus(result.is_pinned ? 'Post pinned!' : 'Post unpinned.', 'success');
		if (state.circleView.currentCircle?._id) {
			await resetAndRenderCircleFeed(state.circleView.currentCircle._id);
		} else {
			await resetAndRenderDashboardFeed();
		}
	} catch (e) {
		showStatus(e.message, 'danger');
	}
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
					el.querySelector('.d-flex span:first-child').insertAdjacentHTML('beforeend', ' <i class="bi bi-check-circle-fill"></i>');
				}
			});
			postWrapper.querySelector('.text-muted').textContent = `Total votes: ${totalVotes}`;
		}
	} catch (e) {
		showStatus(e.message, 'danger');
	}
}

let ytPlaylistPlayer = null;

function openPlaylistPlayerModal(playlist) {
	if (!playlist || !playlist.videos || playlist.videos.length === 0) {
		showStatus("This playlist is empty or invalid.", "warning");
		return;
	}
	const playlistPlayerModal = bootstrap.Modal.getOrCreateInstance(document.getElementById('playlistPlayerModal'));
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
<div class="playlist-queue-item list-group-item d-flex align-items-center gap-3 ${isActive}" data-index="${index}">
<span class="text-muted fw-bold">${index + 1}</span>
<img src="${video.imageSrc}" width="100" class="rounded" alt="${video.title}">
<div class="flex-grow-1" style="min-width: 0;">
<p class="mb-0 small fw-bold text-truncate">${video.title}</p>
</div>
</div>`;
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
	}, () => `<div class="yt-search-result-skeleton"></div>`).join('');
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
		container.innerHTML = '<p class="text-muted small text-center">No videos found.</p>';
		return;
	}
	const addedVideoIds = new Set(state.postCreation.playlist.videos.map(v => v.id));
	container.innerHTML = results.map(video => {
		const isAdded = addedVideoIds.has(video.id);
		const videoData = JSON.stringify(video).replace(/'/g, "&apos;");
		return `
<div class="yt-search-result d-flex justify-content-between align-items-center">
<div class="d-flex align-items-center" style="overflow: hidden;">
<img src="${video.imageSrc}" width="80" class="me-2 rounded" alt="thumbnail">
<small class="text-truncate">${video.title}</small>
</div>
<button type="button" class="btn ${isAdded ? 'btn-success' : 'btn-primary'} btn-sm py-0" data-action="add-video-to-playlist" data-video='${videoData}' ${isAdded ? 'disabled' : ''}>
${isAdded ? 'Added' : '<i class="bi bi-plus-lg"></i>'}
</button>
</div>`;
	}).join('');
}

function renderSelectedPlaylistVideos(container) {
	const videos = state.postCreation.playlist.videos;
	if (videos.length === 0) {
		container.innerHTML = '<p class="text-muted small text-center">Added videos will appear here. You can drag to reorder.</p>';
		return;
	}
	container.innerHTML = videos.map(video => `
<div class="yt-selected-video d-flex justify-content-between align-items-center" draggable="true" data-video-id="${video.id}">
<div class="d-flex align-items-center" style="overflow: hidden;">
<i class="bi bi-grip-vertical me-2"></i>
<img src="${video.imageSrc}" width="80" class="me-2 rounded" alt="thumbnail">
<small class="text-truncate">${video.title}</small>
</div>
<button type="button" class="btn btn-danger btn-sm py-0" data-action="remove-video-from-playlist" data-video-id="${video.id}"><i class="bi bi-trash"></i></button>
</div>
`).join('');
	container.dataset.videos = JSON.stringify(videos);
}

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
			const newVideosOrder = videoElements.map(el => state.postCreation.playlist.videos.find(v => v.id === el.dataset.videoId));
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
				} : closest;
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

const chatManager = {
	currentCircleId: null,
	isLoading: false,
	hasMore: true,
	skip: 0,
	limit: 50,

	async init(circleId) {
		this.currentCircleId = circleId;
		this.reset();
		document.getElementById('chatMessages').innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
		await this.fetchHistory(true);
	},

	reset() {
		this.isLoading = false;
		this.hasMore = true;
		this.skip = 0;
	},

	async fetchHistory(isInitial = false) {
		if (this.isLoading || !this.hasMore) return;
		this.isLoading = true;
		try {
			const data = await apiFetch(`/circles/${this.currentCircleId}/chat?skip=${this.skip}&limit=${this.limit}`);
			if (isInitial) {
				document.getElementById('chatMessages').innerHTML = '';
			}
			data.messages.forEach(msg => this.displayMessage(msg));
			this.hasMore = data.has_more;
			this.skip += data.messages.length;
		} catch (e) {
			console.error("Failed to fetch chat history", e);
			document.getElementById('chatMessages').innerHTML = '<p class="text-danger">Could not load chat history.</p>';
		} finally {
			this.isLoading = false;
		}
	},

	async sendMessage(content) {
		const trimmedContent = content.trim();
		if (!trimmedContent) return;

		const sendBtn = document.getElementById('chatSendBtn');
		setButtonLoading(sendBtn, true);

		try {
			const newMessage = await apiFetch(`/circles/${this.currentCircleId}/chat`, {
				method: 'POST',
				body: JSON.stringify({
					content: trimmedContent
				})
			});
			this.displayMessage(newMessage);
			return true;
		} catch (e) {
			showStatus('Failed to send message.', 'danger');
			return false;
		} finally {
			setButtonLoading(sendBtn, false);
		}
	},

	displayMessage({
		sender_username,
		content,
		timestamp
	}) {
		const messagesDiv = document.getElementById('chatMessages');
		const msgEl = document.createElement('div');
		msgEl.classList.add('chat-message', 'mb-2');

		const isCurrentUser = sender_username === state.currentUser.username;
		msgEl.classList.toggle('text-end', isCurrentUser);

		const formattedTimestamp = new Date(timestamp).toLocaleTimeString([], {
			hour: '2-digit',
			minute: '2-digit'
		});

		msgEl.innerHTML = `
<div>
<strong class="${isCurrentUser ? 'text-primary' : ''}">${isCurrentUser ? 'You' : sender_username}</strong>
<small class="text-muted ms-2">${formattedTimestamp}</small>
</div>
<p class="mb-0 p-2 rounded bg-opacity-10 ${isCurrentUser ? 'bg-primary' : 'bg-secondary'}" style="display: inline-block; text-align: left; max-width: 80%;">${content}</p>
`;
		messagesDiv.appendChild(msgEl);
		messagesDiv.scrollTop = messagesDiv.scrollHeight;
	},
};

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
	document.getElementById('manageIsPublicSwitch').checked = circle.is_public;
	document.getElementById('managePasswordSwitch').checked = circle.is_password_protected;
	document.getElementById('manageCirclePasswordContainer').classList.toggle('hidden', !circle.is_password_protected);
	document.getElementById('manageCirclePassword').value = '';

	const membersContainer = document.getElementById('manageCircleMembersContainer');
	if (!circle.members || circle.members.length === 0) {
		membersContainer.innerHTML = '<p class="text-muted text-center p-3">No member data available.</p>';
	} else {
		const currentUserRole = circle.user_role;
		membersContainer.innerHTML = circle.members.map(member => {
			let actionButtons = '';
			const canManage = (currentUserRole === 'admin' && member.role !== 'admin') || (currentUserRole === 'moderator' && member.role === 'member');
			if (canManage && member.user_id !== state.currentUser.id) {
				if (member.role === 'member') {
					actionButtons += `<button class="btn btn-sm btn-success" data-action="manage-member-role" data-user-id="${member.user_id}" data-new-role="moderator">Promote to Mod</button>`;
				} else if (member.role === 'moderator') {
					actionButtons += `<button class="btn btn-sm btn-secondary" data-action="manage-member-role" data-user-id="${member.user_id}" data-new-role="member">Demote to Member</button>`;
				}
				actionButtons += `<button class="btn btn-sm btn-danger ms-2" data-action="manage-member-kick" data-user-id="${member.user_id}" data-username="${member.username}">Kick</button>`;
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
	const passwordSwitch = document.getElementById('managePasswordSwitch');
	const payload = {
		name: document.getElementById('manageCircleName').value,
		description: document.getElementById('manageCircleDescription').value,
		is_public: document.getElementById('manageIsPublicSwitch').checked,
	};

	if (passwordSwitch.checked) {
		payload.password = document.getElementById('manageCirclePassword').value || null;
	}

	setButtonLoading(btn, true);
	try {
		await apiFetch(`/circles/${circleId}`, {
			method: 'PATCH',
			body: JSON.stringify(payload)
		});
		showStatus('Circle settings updated successfully!', 'success');
		bootstrap.Modal.getInstance('#manageCircleModal').hide();
		await resetAndRenderCircleFeed(circleId);
		const myCircles = await apiFetch('/circles/mine');
		state.myCircles = myCircles;
		renderMyCircles(myCircles);
	} catch (e) {
		showStatus(e.message, 'danger');
	} finally {
		setButtonLoading(btn, false);
	}
}

async function handleManageMemberRole(btn, userId, newRole) {
	const circleId = document.getElementById('manageCircleId').value;
	// UX Improvement: A custom modal would be a better user experience than a browser confirm().
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
	// UX Improvement: A custom modal would be a better user experience than a browser confirm().
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
		handleRoute();
	} catch (e) {
		showStatus(e.message, 'danger');
	} finally {
		setButtonLoading(btn, false);
	}
}

const renderWishlistStagingArea = () => {
	const container = document.getElementById('wishlistStagingArea');
	if (!container) {
		console.error("Debug: Could not find 'wishlistStagingArea' in the DOM.");
		return;
	}
	const urls = state.postCreation.wishlist.urls;

	if (urls.length === 0) {
		container.innerHTML = '<div class="list-group-item text-muted small text-center">Your added items will appear here.</div>';
		return;
	}

	container.innerHTML = urls.map((url, index) => {
		try {
			const hostname = new URL(url).hostname.replace('www.', '');
			return `
                <div class="list-group-item d-flex justify-content-between align-items-center" data-index="${index}">
                    <div class="d-flex align-items-center text-truncate" style="min-width: 0;">
                        <img src="https://www.google.com/s2/favicons?domain=${hostname}&sz=32" class="favicon me-2" alt="favicon">
                        <span class="url-text text-truncate">${url}</span>
                        <input type="text" class="form-control form-control-sm url-input hidden" value="${url}">
                    </div>
                    <div class="btn-group" style="flex-shrink: 0;">
                        <button class="btn btn-sm btn-secondary" data-action="edit-wishlist-item"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-success hidden" data-action="save-wishlist-item"><i class="bi bi-check-lg"></i></button>
                        <button class="btn btn-sm btn-danger" data-action="remove-wishlist-item"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
            `;
		} catch (e) {
			return `
                <div class="list-group-item d-flex justify-content-between align-items-center text-danger" data-index="${index}">
                    <span class="text-truncate">Invalid URL: ${url}</span>
                    <button class="btn btn-sm btn-danger" data-action="remove-wishlist-item"><i class="bi bi-trash"></i></button>
                </div>
            `;
		}
	}).join('');
};

// UX Improvement: Helper function to initialize Bootstrap Tooltips, especially for dynamic content.
const initTooltips = () => {
	const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
	[...tooltipTriggerList].forEach(tooltipTriggerEl => {
		// Avoid re-initializing the same tooltip, which can cause issues.
		if (!bootstrap.Tooltip.getInstance(tooltipTriggerEl)) {
			new bootstrap.Tooltip(tooltipTriggerEl);
		}
	});
};


document.addEventListener('DOMContentLoaded', () => {
	[
		'#createCircleModal',
		'#createPostModal',
		'#inviteCircleModal',
		'#chatModal',
		'#playlistPlayerModal',
		'#youtubeSearchModal',
		'#manageCircleModal',
		'#seenStatusModal'
	].forEach(id => {
		const modalEl = document.querySelector(id);
		if (modalEl) {
			bootstrap.Modal.getOrCreateInstance(modalEl);
		} else {
			console.warn(`Modal element with ID ${id} was not found and could not be initialized.`);
		}
	});

	// UX Improvement: Initialize tooltips on page load.
	initTooltips();

	// UX Improvement: Add focus management to modals for better accessibility and usability.
	document.getElementById('createCircleModal')?.addEventListener('shown.bs.modal', () => {
		document.getElementById('circleName')?.focus();
	});
	document.getElementById('createPostModal')?.addEventListener('shown.bs.modal', () => {
		document.querySelector('#createTextPost textarea')?.focus();
	});
	document.getElementById('youtubeSearchModal')?.addEventListener('shown.bs.modal', () => {
		document.getElementById('youtubeSearchInput')?.focus();
	});
	document.getElementById('inviteCircleModal')?.addEventListener('shown.bs.modal', () => {
		document.getElementById('inviteLinkInput')?.select();
	});


	const authWelcome = document.getElementById('authWelcome');
	const authFormContainer = document.getElementById('authFormContainer');

	document.getElementById('loginButton').addEventListener('click', () => switchAuthView(authWelcome, authFormContainer));
	document.getElementById('backToWelcomeBtn').addEventListener('click', () => switchAuthView(authFormContainer, authWelcome));
	document.getElementById('loginSubmitButton').addEventListener('click', e => handleAuthAction(e, login));
	document.getElementById('registerSubmitButton').addEventListener('click', e => handleAuthAction(e, register));
	document.getElementById('logoutButton').addEventListener('click', logout);
	document.getElementById('createCircleBtn').addEventListener('click', () => bootstrap.Modal.getOrCreateInstance('#createCircleModal').show());
	document.getElementById('submitCircleButton').addEventListener('click', handleCreateCircle);

	const createPostModalEl = document.getElementById('createPostModal');
	const createPostModal = bootstrap.Modal.getOrCreateInstance(createPostModalEl);

	document.getElementById('togglePostCreatorBtn').addEventListener('click', () => {
		const select = createPostModalEl.querySelector('.circleSelect');
		const options = state.myCircles.map(c => `<option value="${c._id}">${c.name}</option>`).join('');
		select.innerHTML = `<option value="">-- Select a Circle --</option>${options}`;
		createPostModal.show();
	});

	document.body.addEventListener('click', e => {
		const toggleCircleBtn = e.target.closest('#togglePostCreatorCircleBtn');
		if (toggleCircleBtn) {
			const circleId = state.circleView.currentCircle?._id;
			const createPostModal = bootstrap.Modal.getOrCreateInstance(document.getElementById('createPostModal'));
			const select = document.getElementById('createPostModal').querySelector('.circleSelect');

			const options = state.myCircles.map(c =>
				`<option value="${c._id}" ${c._id === circleId ? 'selected' : ''}>${c.name}</option>`
			).join('');
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
			}
		};
        document.getElementById('poll-ai-prompt').value = '';
		document.getElementById('pollQuestionInput').value = '';
		renderPollOptionsUI();

		createPostModalEl.querySelector('.post-main-input').value = '';
		createPostModalEl.querySelector('.wishlistTitleInput').value = '';
		document.getElementById('wishlistLinkInput').value = '';
		document.getElementById('wishlistStagingArea').innerHTML = '<div class="list-group-item text-muted small text-center">Your added items will appear here.</div>';
		createPostModalEl.querySelector('.playlistNameInput').value = '';
		createPostModalEl.querySelector('.selectedPlaylistVideosContainer').innerHTML = '<p class="text-muted small text-center">Added videos will appear here. You can drag to reorder.</p>';
		createPostModalEl.querySelector('.postTags').value = '';

		const defaultTab = new bootstrap.Tab(document.querySelector('#postTypeTabs a[data-post-type="main"]'));
		defaultTab.show();

		document.getElementById('imageUploadPreviewContainer').classList.add('hidden');
		document.getElementById('imageFileInput').value = '';
		document.querySelector('#createImagePost .imageUrlInput').value = '';
	});

	document.querySelectorAll('#postTypeTabs a[data-bs-toggle="tab"]').forEach(tab => {
		tab.addEventListener('shown.bs.tab', event => {
			state.postCreation.type = event.target.dataset.postType;
			if (state.postCreation.type === 'poll') {
				renderPollOptionsUI();
			}
		});
	});

	document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
	document.getElementById('themeToggleBtnLogin').addEventListener('click', toggleTheme);

	document.getElementById('protectWithPasswordSwitch').addEventListener('change', e => {
		document.getElementById('circlePasswordContainer').classList.toggle('hidden', !e.target.checked);
	});

	document.getElementById('copyInviteLinkBtn').addEventListener('click', () => {
		navigator.clipboard.writeText(document.getElementById('inviteLinkInput').value);
		showStatus('Invite link copied!', 'success');
	});

	document.getElementById('dashboardSortSelect').addEventListener('change', (e) => {
		state.dashboardFeed.sortBy = e.target.value;
		resetAndRenderDashboardFeed();
	});
	document.getElementById('dashboardTagFilter').addEventListener('input', debounce(e => {
		state.dashboardFeed.filter.tags = e.target.value;
		resetAndRenderDashboardFeed();
	}, 500));

	document.getElementById('youtubeSearchBtn').addEventListener('click', e => handleYouTubeSearch(e.currentTarget));
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

	document.getElementById('playlistPlayerModal').addEventListener('hidden.bs.modal', () => {
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

	document.getElementById('chatSendBtn').addEventListener('click', async () => {
		const input = document.getElementById('chatInput');
		if (input.value) {
			const success = await chatManager.sendMessage(input.value);
			if (success) {
				input.value = '';
			}
		}
	});

	document.getElementById('chatInput').addEventListener('keypress', async (e) => {
		if (e.key === 'Enter') {
			e.preventDefault();
			const input = document.getElementById('chatInput');
			if (input.value) {
				const success = await chatManager.sendMessage(input.value);
				if (success) {
					input.value = '';
				}
			}
		}
	});

	window.addEventListener('hashchange', handleRoute);

	document.body.addEventListener('click', e => {
		const link = e.target.closest('a');
		if (link && link.getAttribute('href') === '#') {
			e.preventDefault();
			if (link.classList.contains('btn')) {
				window.location.hash = '';
			}
		}

		const joinBtn = e.target.closest('#joinCircleSubmitBtn');
		if (joinBtn) {
			handleJoinCircle(joinBtn.dataset.circleId);
			return;
		}

		const target = e.target.closest('[data-action]');
		if (!target) return;
		const {
			action,
			...data
		} = target.dataset;

		switch (action) {
			case 'show-seen-status':
				handleShowSeenStatus(data.postId);
				break;
			case 'delete-post':
				handleDeletePost(data.postId, data.circleId);
				break;
			case 'filter-feed':
				if (window.location.hash !== '') window.location.hash = '';
				state.dashboardFeed.filter.circle_id = data.circleId || null;
				renderMyCircles(state.myCircles);
				resetAndRenderDashboardFeed();
				break;
			case 'invite-to-circle':
				handleInviteToCircle(data.circleId);
				break;
			case 'open-chat':
				bootstrap.Modal.getOrCreateInstance('#chatModal').show();
				chatManager.init(data.circleId);
				break;
			case 'open-yt-search':
				bootstrap.Modal.getOrCreateInstance(document.getElementById('youtubeSearchModal')).show();
				break;
			case 'pin-post':
				handlePinPost(data.postId);
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
					const playlistDataString = data.playlist.replace(/&quot;/g, '"').replace(/&apos;/g, "'");
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
			case 'add-video-to-playlist':
				{
					const video = JSON.parse(data.video.replace(/&apos;/g, "'"));
					state.postCreation.playlist.videos.push(video);
					target.textContent = 'Added';
					target.disabled = true;
					target.classList.remove('btn-primary');
					target.classList.add('btn-success');
					const container = document.querySelector('.selectedPlaylistVideosContainer');
					renderSelectedPlaylistVideos(container);
					break;
				}
			case 'remove-video-from-playlist':
				{
					state.postCreation.playlist.videos = state.postCreation.playlist.videos.filter(v => v.id !== data.videoId);
					const container = document.querySelector('.selectedPlaylistVideosContainer');
					renderSelectedPlaylistVideos(container);
					const searchResultsContainer = document.getElementById('youtubeSearchResultsContainer');
					const correspondingAddButton = searchResultsContainer.querySelector(`[data-video*='"id":"${data.videoId}"']`);
					if (correspondingAddButton) {
						correspondingAddButton.innerHTML = '<i class="bi bi-plus-lg"></i>';
						correspondingAddButton.disabled = false;
						correspondingAddButton.classList.add('btn-primary');
						correspondingAddButton.classList.remove('btn-success');
					}
					break;
				}
			case 'add-wishlist-item':
				{
					const input = document.getElementById('wishlistLinkInput');
					const url = input.value.trim();
					if (url) {
						try {
							new URL(url); // Basic validation
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
		}
	});

	document.getElementById('saveCircleSettingsBtn').addEventListener('click', (e) => handleUpdateCircleSettings(e.currentTarget));
	document.getElementById('deleteCircleConfirmationInput').addEventListener('input', (e) => {
		const circleName = document.getElementById('confirmDeleteCircleName').textContent;
		document.getElementById('deleteCircleBtn').disabled = e.target.value !== circleName;
	});
	document.getElementById('deleteCircleBtn').addEventListener('click', (e) => handleDeleteCircle(e.currentTarget));
	document.getElementById('managePasswordSwitch').addEventListener('change', (e) => {
		document.getElementById('manageCirclePasswordContainer').classList.toggle('hidden', !e.target.checked);
	});

	// Renders the manual poll editor based on the current state
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
                <input type="text" class="form-control poll-option-input" data-index="${index}" value="${optionText}" placeholder="Option ${index + 1}">
                <button class="btn btn-outline-danger" type="button" data-action="remove-poll-option" data-index="${index}" ${options.length <= 2 ? 'disabled' : ''}>
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `).join('');

		const addBtn = document.getElementById('addPollOptionBtn');
		if (addBtn) {
			// UX Improvement: Hide the button when max options are reached, instead of just disabling it.
			addBtn.classList.toggle('hidden', options.length >= 5);
		}
	}

	// Handles AI suggestion for the poll
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

			// Update the state with AI suggestions, capping options at 5
			state.postCreation.pollData.question = data.question;
			state.postCreation.pollData.options = data.options.slice(0, 5).map(opt => opt.text);
			
			// Re-render the manual editor with the new data
			renderPollOptionsUI();

		} catch (error) {
			showStatus('Could not generate poll from text. Please try rephrasing.', 'danger');
		} finally {
			setButtonLoading(btn, false);
		}
	}

	// Event delegation for poll option input changes
	document.getElementById('createPollPost').addEventListener('input', (e) => {
		if (e.target.matches('#pollQuestionInput')) {
			state.postCreation.pollData.question = e.target.value;
		}
		if (e.target.matches('.poll-option-input')) {
			const index = parseInt(e.target.dataset.index, 10);
			state.postCreation.pollData.options[index] = e.target.value;
		}
	});

	initTheme();
	handleRoute();
});

