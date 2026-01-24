// Image Modal functionality
let currentZoom = 1;
let isDragging = false;
const dragStart = { x: 0, y: 0 };
const dragOffset = { x: 0, y: 0 };

// Image gallery data
const imageGallery = [
  {
    src: '/assets/images/problem.svg',
    alt: 'Problem scenario showing frustrated stakeholders dealing with slow traditional workflows',
    title: 'The Problem',
  },
  {
    src: '/assets/images/solution.svg',
    alt: 'Solution scenario showing Rediacc platform with instant production clones',
    title: 'The Solution',
  },
];

let currentImageIndex = 0;
let imageModalTrigger = null;

function trapFocusInModal(modal, e) {
  const focusableEls = modal.querySelectorAll(
    'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
  );
  if (focusableEls.length === 0) return;
  const first = focusableEls[0];
  const last = focusableEls[focusableEls.length - 1];

  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function handleImageModalKeydown(modal, e) {
  if (modal.getAttribute('aria-hidden') !== 'false') return;

  if (e.key === 'Tab') {
    trapFocusInModal(modal, e);
    return;
  }

  const keyActions = {
    Escape: closeImageModal,
    ArrowLeft: previousImage,
    ArrowRight: nextImage,
    '+': zoomIn,
    '=': zoomIn,
    '-': zoomOut,
    0: resetZoom,
  };

  const action = keyActions[e.key];
  if (action) {
    if (e.key !== 'Escape') e.preventDefault();
    action();
  }
}

function initImageModal() {
  const modal = document.getElementById('image-modal');
  const imageContainer = document.querySelector('.image-container');
  const modalImage = document.getElementById('modal-image');

  if (!modal || !imageContainer || !modalImage) return;

  // Button event listeners
  const closeBtn = document.getElementById('image-modal-close-btn');
  const prevBtn = document.getElementById('image-modal-prev-btn');
  const nextBtn = document.getElementById('image-modal-next-btn');
  const zoomInBtn = document.getElementById('image-modal-zoom-in-btn');
  const zoomOutBtn = document.getElementById('image-modal-zoom-out-btn');
  const zoomResetBtn = document.getElementById('image-modal-zoom-reset-btn');

  if (closeBtn) closeBtn.addEventListener('click', closeImageModal);
  if (prevBtn) prevBtn.addEventListener('click', previousImage);
  if (nextBtn) nextBtn.addEventListener('click', nextImage);
  if (zoomInBtn) zoomInBtn.addEventListener('click', zoomIn);
  if (zoomOutBtn) zoomOutBtn.addEventListener('click', zoomOut);
  if (zoomResetBtn) zoomResetBtn.addEventListener('click', resetZoom);

  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeImageModal();
  });

  // Keyboard controls
  document.addEventListener('keydown', (e) => handleImageModalKeydown(modal, e));

  // Mouse wheel zoom
  imageContainer.addEventListener(
    'wheel',
    (e) => {
      if (modal.getAttribute('aria-hidden') !== 'false') return;
      e.preventDefault();
      if (e.deltaY < 0) {
        zoomIn();
      } else {
        zoomOut();
      }
    },
    { passive: false }
  );

  // Drag functionality for zoomed images
  imageContainer.addEventListener('mousedown', startDrag);
  document.addEventListener('mousemove', drag);
  document.addEventListener('mouseup', endDrag);

  // Touch support for mobile
  imageContainer.addEventListener('touchstart', startTouchDrag, { passive: false });
  imageContainer.addEventListener('touchmove', touchDrag, { passive: false });
  imageContainer.addEventListener('touchend', endDrag);
}

// Open image modal
// Note: This function is called from React components and Astro templates via window.openImageModal
function openImageModal(imageSrc, _imageAlt) {
  // Store trigger for focus restoration
  imageModalTrigger = document.activeElement;

  // Find the index of the clicked image
  currentImageIndex = imageGallery.findIndex((img) => img.src === imageSrc);
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
  }, 100);
}

// Expose to global scope for use in HTML onclick and React components
window.openImageModal = openImageModal;

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

  // Restore focus to trigger element
  if (imageModalTrigger && typeof imageModalTrigger.focus === 'function') {
    imageModalTrigger.focus();
    imageModalTrigger = null;
  }
}

// Zoom functions
function zoomIn() {
  if (currentZoom < 3) {
    currentZoom += 0.25;
    updateImageTransform();
  }
}

function zoomOut() {
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

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initImageModal();
});
