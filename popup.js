// API Configuration
let API_BASE_URL = 'http://localhost:8000';

// State management
let state = {
  user: null,
  token: null,
  currentJob: null,
  pollingInterval: null,
  stats: null
};

// DOM Elements
const elements = {
  authSection: document.getElementById('auth-section'),
  dashboardSection: document.getElementById('dashboard-section'),
  connectBtn: document.getElementById('connect-gmail-btn'),
  logoutBtn: document.getElementById('logout-btn'),
  startBtn: document.getElementById('start-btn'),
  cancelBtn: document.getElementById('cancel-btn'),
  refreshBtn: document.getElementById('refresh-btn'),
  settingsBtn: document.getElementById('settings-btn'),
  
  // User info
  userName: document.getElementById('user-name'),
  userEmail: document.getElementById('user-email'),
  userAvatar: document.getElementById('user-avatar'),
  
  // Controls
  modeRadios: document.querySelectorAll('input[name="mode"]'),
  emailScope: document.getElementById('email-scope'),
  
  // Status
  statusBadge: document.getElementById('status-badge'),
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  jobInfo: document.getElementById('job-info'),
  jobId: document.getElementById('job-id'),
  
  // Progress
  progressCard: document.getElementById('progress-card'),
  progressFill: document.getElementById('progress-fill'),
  progressPercentage: document.getElementById('progress-percentage'),
  processedCount: document.getElementById('processed-count'),
  totalCount: document.getElementById('total-count'),
  errorCount: document.getElementById('error-count'),
  errorsCount: document.getElementById('errors-count'),
  
  // Metrics
  totalProcessed: document.getElementById('total-processed'),
  unreadCount: document.getElementById('unread-count'),
  lastRunTime: document.getElementById('last-run-time'),
  categoriesGrid: document.getElementById('categories-grid'),
  
  // Modals
  settingsModal: document.getElementById('settings-modal'),
  settingsClose: document.getElementById('settings-close'),
  settingsSave: document.getElementById('settings-save'),
  apiUrlInput: document.getElementById('api-url'),
  
  // Loading
  loadingOverlay: document.getElementById('loading-overlay'),
  loadingText: document.getElementById('loading-text'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await loadAuthState();
  setupEventListeners();
});

// Settings
async function loadSettings() {
  const result = await chrome.storage.local.get(['apiUrl']);
  if (result.apiUrl) {
    API_BASE_URL = result.apiUrl;
    if (elements.apiUrlInput) {
      elements.apiUrlInput.value = API_BASE_URL;
    }
  }
}

async function saveSettings() {
  const apiUrl = elements.apiUrlInput.value.trim();
  await chrome.storage.local.set({ apiUrl });
  API_BASE_URL = apiUrl;
  showToast('Settings saved', 'success');
  closeModal(elements.settingsModal);
}

// Auth state management
async function loadAuthState() {
  const result = await chrome.storage.local.get(['token', 'user']);
  
  if (result.token && result.user) {
    state.token = result.token;
    state.user = result.user;
    await verifyToken();
  } else {
    showAuthSection();
  }
}

async function verifyToken() {
  try {
    const response = await apiRequest('/api/user/me');
    state.user = response;
    showDashboard();
    await loadStats();
  } catch (error) {
    console.error('Token verification failed:', error);
    await clearAuth();
    showAuthSection();
  }
}

async function clearAuth() {
  state.token = null;
  state.user = null;
  await chrome.storage.local.remove(['token', 'user']);
}

// UI State
function showAuthSection() {
  elements.authSection.style.display = 'block';
  elements.dashboardSection.style.display = 'none';
}

function showDashboard() {
  elements.authSection.style.display = 'none';
  elements.dashboardSection.style.display = 'block';
  
  // Update user info
  if (state.user) {
    elements.userName.textContent = state.user.name || 'User';
    elements.userEmail.textContent = state.user.email || '';
    if (state.user.picture) {
      elements.userAvatar.src = state.user.picture;
    }
  }
}

function showLoading(text = 'Loading...') {
  elements.loadingOverlay.style.display = 'flex';
  elements.loadingText.textContent = text;
}

function hideLoading() {
  elements.loadingOverlay.style.display = 'none';
}

function setupEventListeners() {
  // Auth
  elements.connectBtn.addEventListener('click', handleConnect);
  elements.logoutBtn.addEventListener('click', handleLogout);
  
  // Actions
  elements.startBtn.addEventListener('click', handleStartSorting);
  elements.cancelBtn.addEventListener('click', handleCancelJob);
  elements.refreshBtn.addEventListener('click', handleRefresh);
  
  // Settings
  elements.settingsBtn.addEventListener('click', () => openModal(elements.settingsModal));
  elements.settingsClose.addEventListener('click', () => closeModal(elements.settingsModal));
  elements.settingsSave.addEventListener('click', saveSettings);
  
  // Quick actions
  document.getElementById('open-gmail-btn')?.addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://mail.google.com' });
  });
  
  // FIXED: Listen for auth completion from background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'AUTH_COMPLETE') {
      console.log('✓ Received AUTH_COMPLETE from background');
      state.token = message.data.token;
      state.user = message.data.user;
      showDashboard();
      loadStats();
      showToast('Successfully connected!', 'success');
      
      // Reset button state
      elements.connectBtn.disabled = false;
      elements.connectBtn.innerHTML = '<i class="fas fa-envelope"></i> Connect Gmail';
    }
  });
}

// FIXED: Simplified OAuth handler that uses background script polling
async function handleConnect() {
  try {
    // Disable button
    elements.connectBtn.disabled = true;
    elements.connectBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Opening...';
    
    // Get OAuth URL from backend
    const response = await apiRequest('/auth/google/start', 'GET', null, false);
    const { authorization_url } = response;
    
    console.log('Starting OAuth flow...');
    
    // Tell background script to start polling for auth data
    chrome.runtime.sendMessage({ type: 'START_AUTH_POLLING' }, (response) => {
      console.log('Background script polling started:', response);
    });
    
    // Open OAuth in new tab
    chrome.tabs.create({ url: authorization_url }, (tab) => {
      console.log('OAuth tab opened:', tab.id);
      
      elements.connectBtn.innerHTML = '<i class="fas fa-clock"></i> Waiting for sign-in...';
      
      // Poll storage for auth completion
      const pollInterval = setInterval(async () => {
        const result = await chrome.storage.local.get(['token', 'user']);
        
        if (result.token && result.user) {
          console.log('✓ Auth detected in storage!');
          clearInterval(pollInterval);
          
          state.token = result.token;
          state.user = result.user;
          
          showDashboard();
          await loadStats();
          showToast('Successfully connected!', 'success');
          
          // Reset button
          elements.connectBtn.disabled = false;
          elements.connectBtn.innerHTML = '<i class="fas fa-envelope"></i> Connect Gmail';
          
          // Try to close the OAuth tab
          chrome.tabs.remove(tab.id).catch(() => {
            console.log('OAuth tab already closed');
          });
        }
      }, 1000);
      
      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (!state.token) {
          elements.connectBtn.disabled = false;
          elements.connectBtn.innerHTML = '<i class="fas fa-envelope"></i> Connect Gmail';
          console.log('OAuth polling timeout');
        }
      }, 300000);
      
      // Handle tab closure
      chrome.tabs.onRemoved.addListener(function tabClosedListener(closedTabId) {
        if (closedTabId === tab.id) {
          chrome.tabs.onRemoved.removeListener(tabClosedListener);
          clearInterval(pollInterval);
          
          // Reset button if not authenticated
          if (!state.token) {
            elements.connectBtn.disabled = false;
            elements.connectBtn.innerHTML = '<i class="fas fa-envelope"></i> Connect Gmail';
            showToast('Sign-in cancelled', 'info');
          }
        }
      });
    });
    
    showToast('Complete sign-in in the new tab', 'info');
    
  } catch (error) {
    console.error('OAuth start error:', error);
    showToast('Failed to start OAuth', 'error');
    elements.connectBtn.disabled = false;
    elements.connectBtn.innerHTML = '<i class="fas fa-envelope"></i> Connect Gmail';
  }
}

async function handleLogout() {
  await clearAuth();
  showAuthSection();
  showToast('Logged out', 'info');
}

// Job handling
async function handleStartSorting() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const scope = elements.emailScope.value;
  
  try {
    elements.startBtn.disabled = true;
    showLoading('Starting classification...');
    
    const response = await apiRequest('/api/jobs/start', 'POST', { mode, scope });
    
    state.currentJob = response.job_id;
    updateJobUI(response);
    startPolling();
    
    showToast('Classification started!', 'success');
  } catch (error) {
    showToast('Failed to start classification', 'error');
    console.error(error);
  } finally {
    elements.startBtn.disabled = false;
    hideLoading();
  }
}

async function handleCancelJob() {
  if (!state.currentJob) return;
  
  try {
    await apiRequest(`/api/jobs/${state.currentJob}/cancel`, 'POST');
    stopPolling();
    showToast('Job cancelled', 'info');
    updateStatus('idle', 'Cancelled');
  } catch (error) {
    showToast('Failed to cancel job', 'error');
  }
}

async function handleRefresh() {
  elements.refreshBtn.classList.add('fa-spin');
  await loadStats();
  setTimeout(() => {
    elements.refreshBtn.classList.remove('fa-spin');
  }, 500);
}

// Polling
function startPolling() {
  if (state.pollingInterval) {
    clearInterval(state.pollingInterval);
  }
  
  state.pollingInterval = setInterval(async () => {
    if (state.currentJob) {
      await pollJobStatus();
    }
  }, 2000);
}

function stopPolling() {
  if (state.pollingInterval) {
    clearInterval(state.pollingInterval);
    state.pollingInterval = null;
  }
}

async function pollJobStatus() {
  try {
    const job = await apiRequest(`/api/jobs/${state.currentJob}`);
    updateJobUI(job);
    
    if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
      stopPolling();
      await loadStats();
      
      if (job.status === 'completed') {
        showToast(`Sorted ${job.processed_emails} emails!`, 'success');
      }
    }
  } catch (error) {
    console.error('Polling error:', error);
    stopPolling();
  }
}

// UI Updates
function updateJobUI(job) {
  const { status, total_emails, processed_emails, error_count, category_counts } = job;
  
  // Update status
  updateStatus(status, status.charAt(0).toUpperCase() + status.slice(1));
  
  // Show/hide job info
  if (status === 'running' || status === 'pending') {
    elements.jobInfo.style.display = 'flex';
    elements.jobId.textContent = job.job_id;
    elements.startBtn.disabled = true;
  } else {
    elements.jobInfo.style.display = 'none';
    elements.startBtn.disabled = false;
  }
  
  // Update progress
  if (status === 'running') {
    elements.progressCard.style.display = 'block';
    const percentage = total_emails > 0 ? Math.round((processed_emails / total_emails) * 100) : 0;
    
    elements.progressFill.style.width = `${percentage}%`;
    elements.progressPercentage.textContent = `${percentage}%`;
    elements.processedCount.textContent = processed_emails;
    elements.totalCount.textContent = total_emails;
    
    if (error_count > 0) {
      elements.errorCount.style.display = 'inline';
      elements.errorsCount.textContent = error_count;
    }
  } else {
    elements.progressCard.style.display = 'none';
  }
}

function updateStatus(status, text) {
  elements.statusBadge.textContent = text;
  elements.statusText.textContent = text;
  
  // Remove all status classes
  elements.statusDot.className = 'status-dot';
  
  // Add appropriate class
  if (status === 'running' || status === 'pending') {
    elements.statusDot.classList.add('status-running');
  } else if (status === 'completed') {
    elements.statusDot.classList.add('status-success');
  } else if (status === 'failed') {
    elements.statusDot.classList.add('status-error');
  } else {
    elements.statusDot.classList.add('status-idle');
  }
}

// Stats
async function loadStats() {
  try {
    const [stats, categories] = await Promise.all([
      apiRequest('/api/stats'),
      apiRequest('/api/categories')
    ]);
    
    state.stats = stats;
    updateStatsUI(stats, categories);
  } catch (error) {
    console.error('Failed to load stats:', error);
  }
}

function updateStatsUI(stats, categories) {
  // Update metrics
  elements.totalProcessed.textContent = stats.total_processed || 0;
  elements.unreadCount.textContent = stats.unread_count || 0;
  
  if (stats.last_run_time) {
    const lastRun = new Date(stats.last_run_time);
    elements.lastRunTime.textContent = formatRelativeTime(lastRun);
  } else {
    elements.lastRunTime.textContent = 'never';
  }
  
  // Update categories
  if (stats.category_counts && Object.keys(stats.category_counts).length > 0) {
    renderCategories(stats.category_counts, categories);
  }
}

function renderCategories(counts, categories) {
  const categoryMap = {};
  categories.forEach(cat => {
    categoryMap[cat.name] = cat;
  });
  
  elements.categoriesGrid.innerHTML = Object.entries(counts)
    .map(([name, count]) => {
      const category = categoryMap[name];
      const color = category?.color || '#718096';
      
      return `
        <div class="category-item" style="border-left-color: ${color}">
          <div class="category-name">
            <i class="fas fa-tag" style="color: ${color}"></i>
            ${name.charAt(0).toUpperCase() + name.slice(1)}
          </div>
          <div class="category-count">${count}</div>
        </div>
      `;
    })
    .join('');
}

// Utility functions
async function apiRequest(endpoint, method = 'GET', body = null, requiresAuth = true) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
  };
  
  if (requiresAuth && state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  
  const options = {
    method,
    headers,
  };
  
  if (body) {
    options.body = JSON.stringify(body);
  }
  
  const response = await fetch(url, options);
  
  if (!response.ok) {
    if (response.status === 401) {
      await clearAuth();
      showAuthSection();
      throw new Error('Unauthorized');
    }
    throw new Error(`API error: ${response.statusText}`);
  }
  
  return response.json();
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <i class="fas fa-${getToastIcon(type)}"></i>
    <div class="toast-content">
      <div class="toast-message">${message}</div>
    </div>
    <button class="toast-close">
      <i class="fas fa-times"></i>
    </button>
  `;
  
  const container = document.getElementById('toast-container');
  container.appendChild(toast);
  
  toast.querySelector('.toast-close').addEventListener('click', () => {
    toast.remove();
  });
  
  setTimeout(() => {
    toast.remove();
  }, 5000);
}

function getToastIcon(type) {
  const icons = {
    success: 'check-circle',
    error: 'exclamation-circle',
    info: 'info-circle',
    warning: 'exclamation-triangle'
  };
  return icons[type] || 'info-circle';
}

function openModal(modal) {
  modal.style.display = 'flex';
}

function closeModal(modal) {
  modal.style.display = 'none';
}

function formatRelativeTime(date) {
  const now = new Date();
  const diff = now - date;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return 'just now';
}