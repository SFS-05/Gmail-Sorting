// OAuth callback handler - runs on the callback page
(function() {
  'use strict';
  
  console.log('OAuth handler loaded on:', window.location.href);
  
  // Function to extract and save auth data
  function extractAndSaveAuth() {
    console.log('Attempting to extract auth data...');
    
    // Method 1: Try to find authData in scripts
    const scripts = document.querySelectorAll('script');
    
    for (let script of scripts) {
      const content = script.textContent || script.innerText;
      
      if (content.includes('authData')) {
        console.log('Found script with authData');
        
        try {
          // Extract the token and user info directly using regex
          const tokenMatch = content.match(/token:\s*'([^']+)'/);
          const userIdMatch = content.match(/id:\s*'([^']+)'/);
          const emailMatch = content.match(/email:\s*'([^']+)'/);
          const nameMatch = content.match(/name:\s*'([^']+)'/);
          const pictureMatch = content.match(/picture:\s*'([^']+)'/);
          
          if (tokenMatch && emailMatch) {
            const authData = {
              token: tokenMatch[1],
              user: {
                id: userIdMatch ? userIdMatch[1] : '',
                email: emailMatch[1],
                name: nameMatch ? nameMatch[1] : '',
                picture: pictureMatch ? pictureMatch[1] : ''
              }
            };
            
            console.log('Successfully extracted auth data for:', authData.user.email);
            
            // Send to background script
            chrome.runtime.sendMessage({
              type: 'save_auth',
              data: authData
            }, function(response) {
              if (chrome.runtime.lastError) {
                console.error('Error sending message:', chrome.runtime.lastError);
                return;
              }
              
              console.log('Response from background:', response);
              
              if (response && response.success) {
                console.log('✓ Auth data saved successfully!');
                
                // Visual feedback
                const container = document.querySelector('.container');
                if (container) {
                  const successDiv = document.createElement('div');
                  successDiv.style.cssText = `
                    background: #d1fae5;
                    border: 2px solid #10b981;
                    color: #065f46;
                    padding: 15px;
                    border-radius: 8px;
                    margin-top: 20px;
                    font-weight: 600;
                    font-size: 16px;
                    animation: slideIn 0.3s ease;
                  `;
                  successDiv.innerHTML = '✓ Successfully saved to extension!';
                  container.appendChild(successDiv);
                  
                  const instructions = document.querySelector('.instructions');
                  if (instructions) {
                    instructions.innerHTML = 'Authentication saved!<br>This window will close in 2 seconds...';
                  }
                }
                
                // Close window after 2 seconds
                setTimeout(() => {
                  window.close();
                }, 2000);
              }
            });
            
            return true;
          }
        } catch (e) {
          console.error('Error extracting auth data:', e);
        }
      }
    }
    
    console.log('Could not find auth data in page');
    return false;
  }
  
  // Try immediately
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', extractAndSaveAuth);
  } else {
    extractAndSaveAuth();
  }
  
  // Also try after a delay in case page is still rendering
  setTimeout(extractAndSaveAuth, 500);
  setTimeout(extractAndSaveAuth, 1000);
  
})();