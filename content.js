// Content script for Gmail highlighting
(function() {
  'use strict';

  const CATEGORY_CLASSES = {
    work: 'cloudidian-work',
    personal: 'cloudidian-personal',
    promotion: 'cloudidian-promotion',
    spam: 'cloudidian-spam',
    finance: 'cloudidian-finance',
    security: 'cloudidian-security'
  };

  function highlightEmails() {
    // Gmail uses .zA class for email rows
    const emailRows = document.querySelectorAll('.zA');
    
    emailRows.forEach(row => {
      // Check if already processed
      if (row.dataset.cloudidianProcessed) return;
      
      // Mark as processed
      row.dataset.cloudidianProcessed = 'true';
      
      // Get email labels (Gmail stores them as data attributes)
      const labelElements = row.querySelectorAll('[data-tooltip]');
      
      labelElements.forEach(label => {
        const labelText = label.getAttribute('data-tooltip') || '';
        
        // Check if it's a Cloudidian label
        if (labelText.startsWith('Cloudidian/')) {
          const category = labelText.replace('Cloudidian/', '').toLowerCase();
          
          if (CATEGORY_CLASSES[category]) {
            row.classList.add(CATEGORY_CLASSES[category]);
            row.classList.add('cloudidian-highlight-animation');
          }
        }
      });
    });
  }

  // Observe DOM changes
  const observer = new MutationObserver(() => {
    highlightEmails();
  });

  // Start observing when DOM is ready
  function init() {
    const targetNode = document.body;
    observer.observe(targetNode, {
      childList: true,
      subtree: true
    });
    
    // Initial highlight
    highlightEmails();
  }

  // Wait for DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();