// 🚀 Cloudidian AI Sorter - Background Script
console.log('🚀 Background service worker started');

const API_BASE_URL = 'http://localhost:8000';

// Storage keys
const STORAGE_KEYS = {
  AUTH_TOKEN: 'token',
  USER_DATA: 'user',
  AUTH_PENDING: 'cloudidian_auth_pending',
  AUTH_TIMESTAMP: 'cloudidian_auth_timestamp'
};

// Installation handler
chrome.runtime.onInstalled.addListener((details) => {
  console.log('✓ Cloudidian AI Sorter installed', details);
});

// FIXED: OAuth callback handler using localStorage bridge
// This polls localStorage to detect when OAuth completes
let authCheckInterval = null;

function startAuthPolling() {
  console.log('🔍 Starting auth polling...');
  
  if (authCheckInterval) {
    clearInterval(authCheckInterval);
  }
  
  authCheckInterval = setInterval(async () => {
    try {
      // Get all tabs to check for auth data in localStorage
      const tabs = await chrome.tabs.query({});
      
      for (const tab of tabs) {
        if (tab.url && tab.url.includes('localhost:8000/auth/google/callback')) {
          console.log('📍 Found OAuth callback tab:', tab.id);
          
          // Try to extract auth data from the tab's localStorage
          try {
            const results = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const authPending = localStorage.getItem('cloudidian_auth_pending');
                const authTimestamp = localStorage.getItem('cloudidian_auth_timestamp');
                
                if (authPending && authTimestamp) {
                  // Clear the localStorage items
                  localStorage.removeItem('cloudidian_auth_pending');
                  localStorage.removeItem('cloudidian_auth_timestamp');
                  
                  return {
                    authData: JSON.parse(authPending),
                    timestamp: parseInt(authTimestamp)
                  };
                }
                return null;
              }
            });
            
            if (results && results[0] && results[0].result) {
              const { authData, timestamp } = results[0].result;
              
              // Check if the auth is recent (within last 30 seconds)
              if (Date.now() - timestamp < 30000) {
                console.log('✓ Found fresh auth data!', authData.user.email);
                
                // Save to chrome.storage
                await chrome.storage.local.set({
                  [STORAGE_KEYS.AUTH_TOKEN]: authData.token,
                  [STORAGE_KEYS.USER_DATA]: authData.user
                });
                
                console.log('✓ Auth data saved to chrome.storage');
                
                // Stop polling
                clearInterval(authCheckInterval);
                authCheckInterval = null;
                
                // Close the OAuth tab
                chrome.tabs.remove(tab.id);
                
                // Notify popup to refresh
                chrome.runtime.sendMessage({
                  type: 'AUTH_COMPLETE',
                  data: authData
                }).catch(() => {
                  // Popup might not be open, that's okay
                  console.log('Popup not open to receive AUTH_COMPLETE message');
                });
              }
            }
          } catch (scriptError) {
            console.log('Could not execute script on tab:', scriptError.message);
          }
        }
      }
    } catch (error) {
      console.error('Error in auth polling:', error);
    }
  }, 1000); // Check every second
  
  // Stop polling after 2 minutes
  setTimeout(() => {
    if (authCheckInterval) {
      console.log('⏱ Auth polling timeout');
      clearInterval(authCheckInterval);
      authCheckInterval = null;
    }
  }, 120000);
}

// Listen for messages from popup or content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('📨 Received message:', request.type);
  
  if (request.type === 'START_AUTH_POLLING') {
    startAuthPolling();
    sendResponse({ success: true });
    return true;
  }
  
  if (request.type === 'STOP_AUTH_POLLING') {
    if (authCheckInterval) {
      clearInterval(authCheckInterval);
      authCheckInterval = null;
    }
    sendResponse({ success: true });
    return true;
  }
  
  if (request.type === 'CHECK_AUTH') {
    chrome.storage.local.get([STORAGE_KEYS.AUTH_TOKEN, STORAGE_KEYS.USER_DATA], (result) => {
      sendResponse({
        isAuthenticated: !!(result[STORAGE_KEYS.AUTH_TOKEN] && result[STORAGE_KEYS.USER_DATA]),
        user: result[STORAGE_KEYS.USER_DATA] || null
      });
    });
    return true; // Will respond asynchronously
  }
  
  if (request.type === 'LOGOUT') {
    chrome.storage.local.remove([STORAGE_KEYS.AUTH_TOKEN, STORAGE_KEYS.USER_DATA], () => {
      console.log('✓ User logged out');
      sendResponse({ success: true });
    });
    return true;
  }
  
  if (request.type === 'START_CLASSIFICATION') {
    handleClassification(request.data, sendResponse);
    return true; // Will respond asynchronously
  }
});

// Handle classification job
async function handleClassification(jobData, sendResponse) {
  try {
    const { token } = await chrome.storage.local.get(STORAGE_KEYS.AUTH_TOKEN);
    
    if (!token) {
      sendResponse({ success: false, error: 'Not authenticated' });
      return;
    }
    
    const response = await fetch(`${API_BASE_URL}/api/jobs/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(jobData)
    });
    
    const result = await response.json();
    
    if (response.ok) {
      console.log('✓ Classification job started:', result.job_id);
      sendResponse({ success: true, data: result });
    } else {
      console.error('✗ Failed to start job:', result);
      sendResponse({ success: false, error: result.detail || 'Failed to start job' });
    }
  } catch (error) {
    console.error('✗ Classification error:', error);
    sendResponse({ success: false, error: error.message });
  }
}

// Tab update listener - detect OAuth callback pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    if (tab.url.includes('localhost:8000/auth/google/callback')) {
      console.log('🎯 Detected OAuth callback page');
      
      // Start polling for auth data
      if (!authCheckInterval) {
        startAuthPolling();
      }
    }
  }
});

// Startup: Check storage
chrome.storage.local.get(null, (result) => {
  console.log('📦 Storage on startup:', result);
});

console.log('✓ Background script initialized');