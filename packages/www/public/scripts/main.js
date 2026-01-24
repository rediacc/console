// Early Access Landing Page JavaScript

// NOTE: Keep this in sync with src/config/constants.ts
const CONTACT_EMAIL = 'contact@rediacc.com';

document.addEventListener('DOMContentLoaded', () => {
  // Initialize components
  initSmoothScrolling();
  initFormValidation();
  initMessageOverlay();

  // Add loading states
  document.body.classList.add('loaded');
});

// Smooth scrolling for navigation links
function initSmoothScrolling() {
  const navLinks = document.querySelectorAll('a[href^="#"]');

  navLinks.forEach((link) => {
    link.addEventListener('click', function (e) {
      e.preventDefault();

      const targetId = this.getAttribute('href');
      const targetElement = document.querySelector(targetId);

      if (targetElement) {
        const headerHeight = document.querySelector('.nav').offsetHeight;
        const targetPosition = targetElement.offsetTop - headerHeight - 20;

        window.scrollTo({
          top: targetPosition,
          behavior: 'smooth',
        });
      }
    });
  });
}

// Form validation
function initFormValidation() {
  const form = document.querySelector('.form');
  if (!form) return; // Skip if no form exists on the page

  const inputs = form.querySelectorAll('.form-input, .form-select, .form-textarea');

  // Real-time validation
  inputs.forEach((input) => {
    input.addEventListener('blur', () => validateField(input));
    input.addEventListener('input', () => clearFieldError(input));
  });

  // Form submission validation
  form.addEventListener('submit', function (e) {
    e.preventDefault();

    if (validateForm()) {
      submitForm(this);
    }
  });
}

// Validation helper functions
function validateRequired(field, fieldValue, fieldName) {
  if (field.hasAttribute('required') && !fieldValue) {
    return {
      isValid: false,
      errorMessage: `${getFieldLabel(fieldName)} is required.`,
    };
  }
  return { isValid: true, errorMessage: '' };
}

function validateEmail(fieldValue) {
  if (fieldValue) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(fieldValue)) {
      return {
        isValid: false,
        errorMessage: 'Please enter a valid email address.',
      };
    }
  }
  return { isValid: true, errorMessage: '' };
}

function validateMinLength(fieldValue, minLength, fieldLabel) {
  if (fieldValue && fieldValue.length < minLength) {
    return {
      isValid: false,
      errorMessage: `${fieldLabel} must be at least ${minLength} characters long.`,
    };
  }
  return { isValid: true, errorMessage: '' };
}

// Validate individual field
function validateField(field) {
  const fieldGroup = field.closest('.form-group');
  const errorElement = fieldGroup.querySelector('.form-error');
  const fieldName = field.getAttribute('name');
  const fieldValue = field.value.trim();

  let validationResult = { isValid: true, errorMessage: '' };

  // Required field validation
  validationResult = validateRequired(field, fieldValue, fieldName);
  if (!validationResult.isValid) {
    displayFieldError(fieldGroup, errorElement, field, validationResult.errorMessage);
    return false;
  }

  // Field-specific validation
  switch (fieldName) {
    case 'email':
      validationResult = validateEmail(fieldValue);
      break;
    case 'name':
      validationResult = validateMinLength(fieldValue, 2, 'Name');
      break;
    case 'organization':
      validationResult = validateMinLength(fieldValue, 2, 'Organization name');
      break;
  }

  // Display error state
  if (validationResult.isValid) {
    fieldGroup.classList.remove('error');
    errorElement.textContent = '';
    field.setAttribute('aria-invalid', 'false');
    field.removeAttribute('aria-describedby');
    errorElement.removeAttribute('role');
  } else {
    displayFieldError(fieldGroup, errorElement, field, validationResult.errorMessage);
  }

  return validationResult.isValid;
}

// Helper to display field error
function displayFieldError(fieldGroup, errorElement, field, errorMessage) {
  fieldGroup.classList.add('error');
  errorElement.textContent = errorMessage;
  field.setAttribute('aria-invalid', 'true');
  // Link error message to field for screen readers
  errorElement.id ??= field.id ? `${field.id}-error` : `error-${crypto.randomUUID()}`;
  field.setAttribute('aria-describedby', errorElement.id);
  errorElement.setAttribute('role', 'alert');
}

// Clear field error on input
function clearFieldError(field) {
  const fieldGroup = field.closest('.form-group');
  const errorElement = fieldGroup.querySelector('.form-error');

  if (fieldGroup.classList.contains('error') && field.value.trim()) {
    fieldGroup.classList.remove('error');
    errorElement.textContent = '';
    field.setAttribute('aria-invalid', 'false');
    field.removeAttribute('aria-describedby');
    errorElement.removeAttribute('role');
  }
}

// Validate entire form
function validateForm() {
  const form = document.querySelector('.form');
  const requiredFields = form.querySelectorAll('[required]');
  const invalidFields = Array.from(requiredFields).filter((field) => !validateField(field));

  if (invalidFields.length > 0) {
    const firstInvalidField = form.querySelector(
      '.form-group.error .form-input, .form-group.error .form-select'
    );
    firstInvalidField?.focus();
  }

  return invalidFields.length === 0;
}

// Get human-readable field label
function getFieldLabel(fieldName) {
  const labels = {
    name: 'Full Name',
    email: 'Email Address',
    organization: 'Organization',
    role: 'Role',
    'use-case': 'Use Case',
    message: 'Message',
  };

  return labels[fieldName] ?? fieldName;
}

// Form submission
function submitForm(form) {
  const submitButton = form.querySelector('button[type="submit"]');
  const originalButtonText = submitButton.textContent;

  // Show loading state
  submitButton.disabled = true;
  submitButton.textContent = 'Submitting...';
  submitButton.classList.add('loading');

  try {
    // Allow natural form submission to mailto
    form.submit();

    // Show success message with fallback info
    showMessage(
      'success',
      'Thank You!',
      `Your email client should open with the form data. If it doesn't open automatically, please email us at: ${CONTACT_EMAIL}`
    );
    form.reset();
  } catch (error) {
    console.error('Form submission error:', error);
    // Show error message with email address
    showMessage(
      'error',
      'Email Client Issue',
      `Unable to open your email client automatically. Please send your request manually to: ${CONTACT_EMAIL}`
    );
  }

  // Reset button state
  submitButton.disabled = false;
  submitButton.textContent = originalButtonText;
  submitButton.classList.remove('loading');
}

// Message overlay functionality
function initMessageOverlay() {
  const overlay = document.getElementById('message-overlay');
  const closeButton = document.getElementById('message-close');

  if (!overlay || !closeButton) return; // Skip if no message overlay exists on the page

  closeButton.addEventListener('click', hideMessage);

  // Close on escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay.getAttribute('aria-hidden') === 'false') {
      hideMessage();
    }
  });

  // Close on overlay click (but not content click)
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      hideMessage();
    }
  });
}

// Show message overlay
function showMessage(type, title, text) {
  const overlay = document.getElementById('message-overlay');
  const icon = document.getElementById('message-icon');
  const titleElement = document.getElementById('message-title');
  const textElement = document.getElementById('message-text');

  // Set content
  titleElement.textContent = title;
  textElement.textContent = text;

  // Set icon using SVG
  icon.className = `message-icon ${type}`;
  icon.innerHTML =
    type === 'success'
      ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

  // Show overlay
  overlay.setAttribute('aria-hidden', 'false');

  // Focus the close button for accessibility
  setTimeout(() => {
    document.getElementById('message-close').focus();
  }, 100);
}

// Hide message overlay
function hideMessage() {
  const overlay = document.getElementById('message-overlay');
  overlay.setAttribute('aria-hidden', 'true');

  // Return focus to the form
  const form = document.querySelector('.form');
  if (form) {
    const firstInput = form.querySelector('.form-input');
    if (firstInput) {
      firstInput.focus();
    }
  }
}

// Utility function for throttling scroll events
function throttle(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Add scroll-based navigation highlighting
function initScrollHighlighting() {
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-link[href^="#"]');

  const highlightNavigation = throttle(() => {
    const scrollPosition = window.scrollY + 100;

    sections.forEach((section) => {
      const sectionTop = section.offsetTop;
      const sectionHeight = section.offsetHeight;
      const sectionId = section.getAttribute('id');

      if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
        navLinks.forEach((link) => {
          link.classList.remove('active');
          if (link.getAttribute('href') === `#${sectionId}`) {
            link.classList.add('active');
          }
        });
      }
    });
  }, 100);

  window.addEventListener('scroll', highlightNavigation);
}

// Initialize scroll highlighting
document.addEventListener('DOMContentLoaded', () => {
  initScrollHighlighting();
});

// Form enhancement for better UX
function initFormEnhancements() {
  const form = document.querySelector('.form');
  if (!form) return; // Skip if no form exists on the page

  // Auto-format phone numbers (if added later)
  const phoneInputs = form.querySelectorAll('input[type="tel"]');
  phoneInputs.forEach((input) => {
    input.addEventListener('input', (e) => {
      // Remove all non-digits
      let value = e.target.value.replaceAll(/\D/g, '');

      // Format as (XXX) XXX-XXXX
      if (value.length >= 6) {
        value = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6, 10)}`;
      } else if (value.length >= 3) {
        value = `(${value.slice(0, 3)}) ${value.slice(3)}`;
      }

      e.target.value = value;
    });
  });

  // Note: Character counter removed to prevent React hydration mismatch
  // If needed in future, implement it in React component instead
}

// Initialize form enhancements
document.addEventListener('DOMContentLoaded', () => {
  initFormEnhancements();
});

// Accessibility improvements
function initAccessibilityFeatures() {
  // Skip to main content link
  const skipLink = document.createElement('a');
  skipLink.href = '#hero';
  skipLink.textContent = 'Skip to main content';
  skipLink.className = 'sr-only';
  skipLink.addEventListener('focus', function () {
    this.classList.remove('sr-only');
  });
  skipLink.addEventListener('blur', function () {
    this.classList.add('sr-only');
  });

  document.body.insertBefore(skipLink, document.body.firstChild);

  // Announce form errors to screen readers
  const form = document.querySelector('.form');
  if (form) {
    const errorAnnouncer = document.createElement('div');
    errorAnnouncer.setAttribute('aria-live', 'polite');
    errorAnnouncer.setAttribute('aria-atomic', 'true');
    errorAnnouncer.className = 'sr-only';
    errorAnnouncer.id = 'error-announcer';

    form.appendChild(errorAnnouncer);
  }
}

// Initialize accessibility features
document.addEventListener('DOMContentLoaded', () => {
  initAccessibilityFeatures();
});

// Progressive enhancement check
if ('IntersectionObserver' in window) {
  // Add fade-in animations for elements coming into view
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px',
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('fade-in');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  // Observe sections for animation
  // Note: Removed .early-access-text to prevent React hydration mismatch
  document.addEventListener('DOMContentLoaded', () => {
    const animatedElements = document.querySelectorAll('.solution-card, .timeline-item');
    animatedElements.forEach((el) => observer.observe(el));
  });
}
