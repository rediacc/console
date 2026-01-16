// Early Access Landing Page JavaScript

// NOTE: Keep this in sync with src/config/constants.ts
const CONTACT_EMAIL = 'contact@rediacc.com';

document.addEventListener('DOMContentLoaded', function() {
    // Initialize components
    initSmoothScrolling();
    initFormValidation();
    initMessageOverlay();
    initImageModal();

    // Add loading states
    document.body.classList.add('loaded');
});

// Smooth scrolling for navigation links
function initSmoothScrolling() {
    const navLinks = document.querySelectorAll('a[href^="#"]');

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();

            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);

            if (targetElement) {
                const headerHeight = document.querySelector('.nav').offsetHeight;
                const targetPosition = targetElement.offsetTop - headerHeight - 20;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
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
    inputs.forEach(input => {
        input.addEventListener('blur', () => validateField(input));
        input.addEventListener('input', () => clearFieldError(input));
    });

    // Form submission validation
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        if (validateForm()) {
            submitForm(this);
        }
    });
}

// Validate individual field
function validateField(field) {
    const fieldGroup = field.closest('.form-group');
    const errorElement = fieldGroup.querySelector('.form-error');
    const fieldName = field.getAttribute('name');
    const fieldValue = field.value.trim();

    let isValid = true;
    let errorMessage = '';

    // Required field validation
    if (field.hasAttribute('required') && !fieldValue) {
        isValid = false;
        errorMessage = `${getFieldLabel(fieldName)} is required.`;
    }

    // Email validation
    if (fieldName === 'email' && fieldValue) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(fieldValue)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address.';
        }
    }

    // Name validation
    if (fieldName === 'name' && fieldValue) {
        if (fieldValue.length < 2) {
            isValid = false;
            errorMessage = 'Name must be at least 2 characters long.';
        }
    }

    // Organization validation
    if (fieldName === 'organization' && fieldValue) {
        if (fieldValue.length < 2) {
            isValid = false;
            errorMessage = 'Organization name must be at least 2 characters long.';
        }
    }

    // Display error state
    if (!isValid) {
        fieldGroup.classList.add('error');
        errorElement.textContent = errorMessage;
        field.setAttribute('aria-invalid', 'true');
    } else {
        fieldGroup.classList.remove('error');
        errorElement.textContent = '';
        field.setAttribute('aria-invalid', 'false');
    }

    return isValid;
}

// Clear field error on input
function clearFieldError(field) {
    const fieldGroup = field.closest('.form-group');
    const errorElement = fieldGroup.querySelector('.form-error');

    if (fieldGroup.classList.contains('error') && field.value.trim()) {
        fieldGroup.classList.remove('error');
        errorElement.textContent = '';
        field.setAttribute('aria-invalid', 'false');
    }
}

// Validate entire form
function validateForm() {
    const form = document.querySelector('.form');
    const requiredFields = form.querySelectorAll('[required]');
    let isFormValid = true;

    requiredFields.forEach(field => {
        if (!validateField(field)) {
            isFormValid = false;
        }
    });

    // Focus first invalid field
    if (!isFormValid) {
        const firstInvalidField = form.querySelector('.form-group.error .form-input, .form-group.error .form-select');
        if (firstInvalidField) {
            firstInvalidField.focus();
        }
    }

    return isFormValid;
}

// Get human-readable field label
function getFieldLabel(fieldName) {
    const labels = {
        'name': 'Full Name',
        'email': 'Email Address',
        'organization': 'Organization',
        'role': 'Role',
        'use-case': 'Use Case',
        'message': 'Message'
    };

    return labels[fieldName] || fieldName;
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
        showMessage('success', 'Thank You!', `Your email client should open with the form data. If it doesn't open automatically, please email us at: ${CONTACT_EMAIL}`);
        form.reset();
    } catch (error) {
        console.error('Form submission error:', error);
        // Show error message with email address
        showMessage('error', 'Email Client Issue', `Unable to open your email client automatically. Please send your request manually to: ${CONTACT_EMAIL}`);
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
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && overlay.getAttribute('aria-hidden') === 'false') {
            hideMessage();
        }
    });

    // Close on overlay click (but not content click)
    overlay.addEventListener('click', function(e) {
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

    // Set icon
    icon.className = `message-icon ${type}`;
    icon.textContent = type === 'success' ? '✓' : '✕';

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

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');

            if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
                navLinks.forEach(link => {
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
document.addEventListener('DOMContentLoaded', function() {
    initScrollHighlighting();
});

// Form enhancement for better UX
function initFormEnhancements() {
    const form = document.querySelector('.form');
    if (!form) return; // Skip if no form exists on the page

    // Auto-format phone numbers (if added later)
    const phoneInputs = form.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            // Remove all non-digits
            let value = e.target.value.replace(/\D/g, '');

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
document.addEventListener('DOMContentLoaded', function() {
    initFormEnhancements();
});

// Accessibility improvements
function initAccessibilityFeatures() {
    // Skip to main content link
    const skipLink = document.createElement('a');
    skipLink.href = '#hero';
    skipLink.textContent = 'Skip to main content';
    skipLink.className = 'sr-only';
    skipLink.addEventListener('focus', function() {
        this.classList.remove('sr-only');
    });
    skipLink.addEventListener('blur', function() {
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
document.addEventListener('DOMContentLoaded', function() {
    initAccessibilityFeatures();
});

// Progressive enhancement check
if ('IntersectionObserver' in window) {
    // Add fade-in animations for elements coming into view
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe sections for animation
    // Note: Removed .early-access-text to prevent React hydration mismatch
    document.addEventListener('DOMContentLoaded', function() {
        const animatedElements = document.querySelectorAll('.solution-card, .timeline-item');
        animatedElements.forEach(el => observer.observe(el));
    });
}

// Image Modal functionality
let currentZoom = 1;
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let dragOffset = { x: 0, y: 0 };

// Image gallery data
const imageGallery = [
    {
        src: '/assets/images/problem.svg',
        alt: 'Problem scenario showing frustrated stakeholders dealing with slow traditional workflows',
        title: 'The Problem'
    },
    {
        src: '/assets/images/solution.svg',
        alt: 'Solution scenario showing Rediacc platform with instant production clones',
        title: 'The Solution'
    }
];

let currentImageIndex = 0;

function initImageModal() {
    const modal = document.getElementById('image-modal');
    const imageContainer = document.querySelector('.image-container');
    const modalImage = document.getElementById('modal-image');

    if (!modal || !imageContainer || !modalImage) return; // Skip if no image modal exists on the page

    // Keyboard controls
    document.addEventListener('keydown', function(e) {
        if (modal.getAttribute('aria-hidden') === 'false') {
            switch(e.key) {
                case 'Escape':
                    closeImageModal();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    previousImage();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    nextImage();
                    break;
                case '+':
                case '=':
                    e.preventDefault();
                    zoomIn();
                    break;
                case '-':
                    e.preventDefault();
                    zoomOut();
                    break;
                case '0':
                    e.preventDefault();
                    resetZoom();
                    break;
            }
        }
    });

    // Mouse wheel zoom
    if (imageContainer) {
        imageContainer.addEventListener('wheel', function(e) {
            if (modal.getAttribute('aria-hidden') === 'false') {
                e.preventDefault();
                if (e.deltaY < 0) {
                    zoomIn();
                } else {
                    zoomOut();
                }
            }
        }, { passive: false }); // Explicitly non-passive because we call preventDefault()

        // Drag functionality for zoomed images
        imageContainer.addEventListener('mousedown', startDrag);
        document.addEventListener('mousemove', drag);
        document.addEventListener('mouseup', endDrag);

        // Touch support for mobile
        imageContainer.addEventListener('touchstart', startTouchDrag, { passive: false });
        imageContainer.addEventListener('touchmove', touchDrag, { passive: false });
        imageContainer.addEventListener('touchend', endDrag);
    }
}

// Open image modal
function openImageModal(imageSrc, imageAlt) {
    // Find the index of the clicked image
    currentImageIndex = imageGallery.findIndex(img => img.src === imageSrc);
    if (currentImageIndex === -1) currentImageIndex = 0; // Fallback to first image

    const modal = document.getElementById('image-modal');
    showCurrentImage();
    modal.setAttribute('aria-hidden', 'false');

    // Prevent body scroll when modal is open
    document.body.style.overflow = 'hidden';


    // Focus the close button for accessibility
    setTimeout(() => {
        const closeButton = modal.querySelector('.image-modal-close');
        if (closeButton) {
            closeButton.focus();
        }
    }, 300);
}

// Show current image and update UI
function showCurrentImage() {
    const modalImage = document.getElementById('modal-image');
    const indicator = document.getElementById('image-indicator');
    const prevBtn = document.querySelector('.nav-prev');
    const nextBtn = document.querySelector('.nav-next');

    const currentImage = imageGallery[currentImageIndex];

    modalImage.src = currentImage.src;
    modalImage.alt = currentImage.alt;
    indicator.textContent = `${currentImageIndex + 1} / ${imageGallery.length}`;

    // Update navigation button states
    prevBtn.disabled = currentImageIndex === 0;
    nextBtn.disabled = currentImageIndex === imageGallery.length - 1;

    // Reset zoom when changing images
    resetZoom();
}

// Navigation functions
function previousImage() {
    if (currentImageIndex > 0) {
        currentImageIndex--;
        showCurrentImage();
    }
}

function nextImage() {
    if (currentImageIndex < imageGallery.length - 1) {
        currentImageIndex++;
        showCurrentImage();
    }
}


// Close image modal
function closeImageModal() {
    const modal = document.getElementById('image-modal');
    const modalImage = document.getElementById('modal-image');

    modal.setAttribute('aria-hidden', 'true');
    modalImage.src = '';
    modalImage.alt = '';

    // Reset zoom and drag
    resetZoom();

    // Restore body scroll
    document.body.style.overflow = '';
}

// Zoom functions
function zoomIn() {
    const modalImage = document.getElementById('modal-image');
    if (currentZoom < 3) {
        currentZoom += 0.25;
        updateImageTransform();
    }
}

function zoomOut() {
    const modalImage = document.getElementById('modal-image');
    if (currentZoom > 0.5) {
        currentZoom -= 0.25;
        updateImageTransform();

        // Reset drag offset if zooming out significantly
        if (currentZoom <= 1) {
            dragOffset.x = 0;
            dragOffset.y = 0;
        }
    }
}

function resetZoom() {
    currentZoom = 1;
    dragOffset.x = 0;
    dragOffset.y = 0;
    updateImageTransform();
}

function updateImageTransform() {
    const modalImage = document.getElementById('modal-image');
    if (modalImage) {
        modalImage.style.transform = `translate(${dragOffset.x}px, ${dragOffset.y}px) scale(${currentZoom})`;
    }
}

// Drag functions
function startDrag(e) {
    if (currentZoom > 1) {
        isDragging = true;
        dragStart.x = e.clientX - dragOffset.x;
        dragStart.y = e.clientY - dragOffset.y;
        e.preventDefault();
    }
}

function drag(e) {
    if (isDragging && currentZoom > 1) {
        dragOffset.x = e.clientX - dragStart.x;
        dragOffset.y = e.clientY - dragStart.y;
        updateImageTransform();
        e.preventDefault();
    }
}

function endDrag() {
    isDragging = false;
}

// Touch drag functions
function startTouchDrag(e) {
    if (currentZoom > 1 && e.touches.length === 1) {
        isDragging = true;
        const touch = e.touches[0];
        dragStart.x = touch.clientX - dragOffset.x;
        dragStart.y = touch.clientY - dragOffset.y;
        e.preventDefault();
    }
}

function touchDrag(e) {
    if (isDragging && currentZoom > 1 && e.touches.length === 1) {
        const touch = e.touches[0];
        dragOffset.x = touch.clientX - dragStart.x;
        dragOffset.y = touch.clientY - dragStart.y;
        updateImageTransform();
        e.preventDefault();
    }
}

