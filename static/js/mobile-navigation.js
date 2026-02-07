/**
 * Mobile Navigation Component
 * Reusable bottom navigation for mobile-first design
 */

class MobileNavigation {
    constructor(activeTab = 'home') {
        this.activeTab = activeTab;
        this.navItems = [
            {
                id: 'home',
                label: 'Home',
                icon: '🏠',
                href: '/conversation-select'
            },
            {
                id: 'album',
                label: 'Album',
                icon: '🎴',
                href: '/sticker-album'
            },
            {
                id: 'activity',
                label: 'Activity',
                icon: '📊',
                href: '/dashboard'
            }
        ];
        this.init();
    }

    init() {
        this.createNavigationHTML();
        this.attachEventListeners();
        this.updateActiveState();
    }

    createNavigationHTML() {
        const navHTML = `
            <nav class="bottom-navigation">
                <div class="bottom-nav-container">
                    ${this.navItems.map(item => `
                        <a href="${item.href}" 
                           class="bottom-nav-item ${item.id === this.activeTab ? 'active' : ''}"
                           data-nav-id="${item.id}">
                            <div class="bottom-nav-icon">${item.icon}</div>
                            <div class="bottom-nav-label">${item.label}</div>
                        </a>
                    `).join('')}
                </div>
            </nav>
        `;

        // Insert navigation at the end of body
        document.body.insertAdjacentHTML('beforeend', navHTML);
    }

    attachEventListeners() {
        const navItems = document.querySelectorAll('.bottom-nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                this.handleNavClick(e);
            });
        });
    }

    handleNavClick(e) {
        const navId = e.currentTarget.getAttribute('data-nav-id');
        
        // Update active state immediately for better UX
        this.setActiveTab(navId);
        
        // Let the browser handle the navigation naturally
        // The href attribute will handle the page navigation
    }

    setActiveTab(tabId) {
        this.activeTab = tabId;
        this.updateActiveState();
    }

    updateActiveState() {
        const navItems = document.querySelectorAll('.bottom-nav-item');
        navItems.forEach(item => {
            const itemId = item.getAttribute('data-nav-id');
            if (itemId === this.activeTab) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    // Method to update active tab from outside (useful for page-specific logic)
    static setActive(tabId) {
        const navItems = document.querySelectorAll('.bottom-nav-item');
        navItems.forEach(item => {
            const itemId = item.getAttribute('data-nav-id');
            if (itemId === tabId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }
}

/**
 * Profile Avatar Component
 * Handles the fun kids avatar in the top bar
 */
class ProfileAvatar {
    constructor() {
        this.avatars = ['🦄', '🐻', '🐯', '🦁', '🐸', '🐨', '🐰', '🐼'];
        this.currentAvatar = this.getStoredAvatar() || this.getRandomAvatar();
        this.init();
    }

    init() {
        this.createAvatarHTML();
        this.attachEventListeners();
        this.loadUserData();
    }

    getRandomAvatar() {
        return this.avatars[Math.floor(Math.random() * this.avatars.length)];
    }

    getStoredAvatar() {
        return localStorage.getItem('userAvatar');
    }

    storeAvatar(avatar) {
        localStorage.setItem('userAvatar', avatar);
    }

    createAvatarHTML() {
        const avatarHTML = `
            <div class="profile-avatar" id="profileButton">
                <span id="avatarIcon">${this.currentAvatar}</span>
            </div>
            <div class="profile-dropdown" id="dropdownMenu">
                <div class="dropdown-header">
                    <div class="dropdown-user-name" id="dropdownUserName">User</div>
                    <div class="dropdown-user-email" id="dropdownUserEmail">user@example.com</div>
                </div>
                <a href="/profile" class="dropdown-item">Profile</a>
                <a href="/dashboard" class="dropdown-item">Dashboard</a>
                <a href="/logout" class="dropdown-item danger">Sign out</a>
            </div>
        `;

        // Find the mobile top bar and insert avatar while preserving existing content
        const topBar = document.querySelector('.mobile-top-bar');
        if (topBar) {
            // Store existing content before replacing
            const existingContent = topBar.innerHTML;
            
            // Only replace if we haven't already added the profile components
            if (!topBar.querySelector('#profileButton')) {
                // If there's existing content (like history button), preserve it
                if (existingContent.trim()) {
                    topBar.insertAdjacentHTML('beforeend', avatarHTML);
                } else {
                    topBar.innerHTML = avatarHTML;
                }
            }
        }
    }

    attachEventListeners() {
        // Profile button click
        document.addEventListener('click', (e) => {
            const profileButton = document.getElementById('profileButton');
            const dropdown = document.getElementById('dropdownMenu');
            
            if (!profileButton || !dropdown) return;

            if (profileButton.contains(e.target)) {
                e.stopPropagation();
                dropdown.classList.toggle('show');
            } else {
                dropdown.classList.remove('show');
            }
        });

        // Avatar cycling (fun feature - double tap to change)
        let tapCount = 0;
        document.getElementById('profileButton')?.addEventListener('click', (e) => {
            tapCount++;
            setTimeout(() => {
                if (tapCount === 2) {
                    this.cycleAvatar();
                }
                tapCount = 0;
            }, 300);
        });
    }

    cycleAvatar() {
        const currentIndex = this.avatars.indexOf(this.currentAvatar);
        const nextIndex = (currentIndex + 1) % this.avatars.length;
        this.currentAvatar = this.avatars[nextIndex];
        
        const avatarIcon = document.getElementById('avatarIcon');
        if (avatarIcon) {
            avatarIcon.textContent = this.currentAvatar;
            this.storeAvatar(this.currentAvatar);
        }
    }

    async loadUserData() {
        try {
            const response = await fetch('/api/user');
            if (response.ok) {
                const user = await response.json();
                this.updateUserInfo(user);
            }
        } catch (error) {
            console.error('Error loading user data:', error);
        }
    }

    updateUserInfo(user) {
        const userName = document.getElementById('dropdownUserName');
        const userEmail = document.getElementById('dropdownUserEmail');
        
        if (userName) userName.textContent = user.name || 'User';
        if (userEmail) userEmail.textContent = user.email || '';
    }
}

/**
 * Mobile Page Utils
 * Utility functions for mobile page management
 */
class MobilePageUtils {
    static determineCurrentPage() {
        const path = window.location.pathname;
        
        if (path === '/conversation-select' || path === '/') {
            return 'home';
        } else if (path === '/sticker-album') {
            return 'album';
        } else if (path === '/dashboard') {
            return 'activity';
        }

        return 'home'; // default
    }

    static initializePage() {
        // Add mobile design system CSS if not already added
        if (!document.querySelector('link[href*="mobile-design-system.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = '/static/css/mobile-design-system.css';
            document.head.appendChild(link);
        }

        // Initialize components based on page
        const currentPage = this.determineCurrentPage();
        
        // Initialize navigation
        new MobileNavigation(currentPage);
        
        // Initialize profile avatar
        new ProfileAvatar();
        
        // Add page-specific classes
        document.body.classList.add('mobile-page', `page-${currentPage}`);
    }

    static showPageTransition() {
        // Add a subtle transition effect when navigating between pages
        document.body.style.opacity = '0.8';
        setTimeout(() => {
            document.body.style.opacity = '1';
        }, 150);
    }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        MobilePageUtils.initializePage();
    });
} else {
    MobilePageUtils.initializePage();
}

// Export for use in other scripts if needed
window.MobileNavigation = MobileNavigation;
window.ProfileAvatar = ProfileAvatar;
window.MobilePageUtils = MobilePageUtils;