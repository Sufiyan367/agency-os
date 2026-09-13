/**
 * Agency OS: CEO Mobile Notification Center & Web Push Controller
 * Output: ES6 JavaScript Module
 */

function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function formatRelativeTime(dateStr) {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diffSec < 45) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch (e) {
    return dateStr;
  }
}

export class NotificationCenterController {
  constructor() {
    this.drawerOpen = false;
    this.currentFilter = 'ALL';
    this.unreadCount = 0;
    this.pollInterval = null;
    this.swRegistration = null;
    this.isPushSubscribed = false;
    this.init();
  }

  async init() {
    this.bindDOM();
    this.fetchUnreadCount();
    this.checkInitialUrlState();
    this.startPolling();
    this.initServiceWorker().catch((err) => console.warn('[NotificationCenter] SW init deferred/error:', err));
  }

  checkInitialUrlState() {
    const hash = window.location.hash || '';
    const params = new URLSearchParams(window.location.search);
    if (hash === '#notifications' || params.get('tab') === 'notifications' || params.get('notif') === '1') {
      setTimeout(() => this.openDrawer(), 300);
    }
  }

  bindDOM() {
    const bellBtn = document.getElementById('btn-notification-center');
    if (bellBtn) {
      bellBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleDrawer();
      };
    }

    const mobileBottomNotifBtn = document.getElementById('mobile-bottom-notif-btn');
    if (mobileBottomNotifBtn) {
      mobileBottomNotifBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleDrawer();
      };
    }

    const closeBtn = document.getElementById('btn-close-notif-drawer');
    if (closeBtn) {
      closeBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.closeDrawer();
      };
    }

    const backdrop = document.getElementById('notification-drawer-backdrop');
    if (backdrop) {
      backdrop.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.closeDrawer();
      };
    }

    const drawer = document.getElementById('notification-drawer');
    if (drawer) {
      drawer.onclick = (e) => e.stopPropagation();
    }

    // Escape key listener
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.drawerOpen) {
        this.closeDrawer();
      }
    });

    // Outside click listener
    document.addEventListener('click', (e) => {
      if (!this.drawerOpen) return;
      if (e.target && e.target.closest && (
        e.target.closest('#notification-drawer') ||
        e.target.closest('#btn-notification-center') ||
        e.target.closest('#mobile-bottom-notif-btn')
      )) {
        return;
      }
      this.closeDrawer();
    });

    const markAllBtn = document.getElementById('btn-mark-all-read');
    if (markAllBtn) {
      markAllBtn.onclick = (e) => {
        e.preventDefault();
        this.markAllRead();
      };
    }

    const pushBtn = document.getElementById('btn-enable-push');
    if (pushBtn) {
      pushBtn.onclick = (e) => {
        e.preventDefault();
        this.subscribePush();
      };
    }

    // Filter pills
    const filterPills = document.querySelectorAll('.notif-filter-pill');
    filterPills.forEach((pill) => {
      pill.onclick = (e) => {
        e.preventDefault();
        const target = e.currentTarget;
        const category = target.dataset.category || 'ALL';
        this.setFilter(category);
      };
    });

    // Test alert triggers
    const testBtns = document.querySelectorAll('.btn-trigger-test-alert');
    testBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const target = e.currentTarget;
        const eventType = target.dataset.eventType || 'TEST_PAYMENT_VERIFIED';
        this.triggerTestEvent(eventType);
      };
    });
  }

  async initServiceWorker() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('[NotificationCenter] Push messaging not supported in this browser.');
      this.updatePushUI('unsupported', 'Push Unsupported');
      return;
    }

    if (Notification.permission === 'denied') {
      this.updatePushUI('blocked', 'Notifications Blocked');
      return;
    }

    try {
      this.swRegistration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      console.log('[NotificationCenter] Service worker registered with scope:', this.swRegistration.scope);

      // Check existing subscription
      const sub = await this.swRegistration.pushManager.getSubscription();
      if (sub) {
        this.isPushSubscribed = true;
        this.updatePushUI('active', '✓ Notifications Active');
      } else {
        this.isPushSubscribed = false;
        this.updatePushUI('idle', 'Enable Mobile Push');
      }

      // Listen for message from service worker
      navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'AGENCY_NOTIFICATION_CLICK') {
          console.log('[NotificationCenter] Handled click message:', event.data);
          this.fetchUnreadCount();
          this.loadNotifications();
        }
      });
    } catch (err) {
      console.error('[NotificationCenter] Service worker registration error:', err);
    }
  }

  async subscribePush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      alert('Web Push is not supported in this browser environment.');
      this.updatePushUI('unsupported', 'Push Unsupported');
      return false;
    }

    if (Notification.permission === 'denied') {
      alert('Notifications are blocked in your browser. Please enable notifications in your browser or site settings.');
      this.updatePushUI('blocked', 'Notifications Blocked');
      return false;
    }

    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        alert('Notification permission was not granted.');
        this.updatePushUI('blocked', 'Permission Denied');
        return false;
      }

      if (!this.swRegistration) {
        this.swRegistration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      }

      // Fetch VAPID key
      const keyResp = await fetch('/api/notifications/vapid-public-key');
      const keyData = await keyResp.json();
      if (!keyData.public_key) {
        throw new Error('Server returned unconfigured VAPID public key.');
      }

      const convertedVapidKey = urlB64ToUint8Array(keyData.public_key);

      const subscription = await this.swRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedVapidKey,
      });

      const p256dhKey = subscription.getKey('p256dh');
      const authKey = subscription.getKey('auth');
      if (!p256dhKey || !authKey) {
        throw new Error('Subscription missing cryptographic keys.');
      }

      const p256dh = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(p256dhKey))))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');

      const auth = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(authKey))))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');

      const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
      const isAndroid = /Android/i.test(navigator.userAgent);
      const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
      let devType = 'desktop_browser';
      let devName = 'Desktop Workstation';
      if (isAndroid) {
        devType = 'mobile_android';
        devName = 'Android Mobile Phone';
      } else if (isIOS) {
        devType = 'mobile_ios';
        devName = 'iOS Apple Device';
      } else if (isMobile) {
        devType = 'mobile_web';
        devName = 'Mobile Browser';
      }

      const regResp = await fetch('/api/notifications/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_name: devName,
          device_type: devType,
          endpoint: subscription.endpoint,
          p256dh: p256dh,
          auth_token: auth,
        }),
      });

      if (!regResp.ok) {
        throw new Error(`Device registration failed with status ${regResp.status}`);
      }

      this.isPushSubscribed = true;
      this.updatePushUI('active', '✓ Notifications Active');
      this.showToast('Push Notifications Active', 'This device will receive critical CEO alerts.', 'success');
      return true;
    } catch (err) {
      console.error('[NotificationCenter] Error subscribing to push:', err);
      alert(`Could not subscribe to push: ${err.message}`);
      return false;
    }
  }

  updatePushUI(state, label) {
    const pushBtn = document.getElementById('btn-enable-push');
    const pushDot = document.getElementById('push-status-dot');
    const pushText = document.getElementById('push-status-text');

    if (pushBtn) {
      if (state === 'active') {
        pushBtn.classList.add('push-active');
        pushBtn.textContent = '✓ Subscribed';
        pushBtn.style.background = 'rgba(16, 185, 129, 0.2)';
        pushBtn.style.color = '#10b981';
        pushBtn.style.border = '1px solid rgba(16, 185, 129, 0.4)';
      } else if (state === 'blocked' || state === 'unsupported') {
        pushBtn.classList.remove('push-active');
        pushBtn.textContent = 'Settings';
        pushBtn.style.background = 'rgba(239, 68, 68, 0.15)';
        pushBtn.style.color = '#ef4444';
        pushBtn.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      } else {
        pushBtn.classList.remove('push-active');
        pushBtn.textContent = 'Enable';
        pushBtn.style.background = '#38bdf8';
        pushBtn.style.color = '#0b0e14';
        pushBtn.style.border = 'none';
      }
    }

    if (pushDot) {
      if (state === 'active') {
        pushDot.style.background = '#10b981';
        pushDot.style.boxShadow = '0 0 8px #10b981';
      } else if (state === 'blocked' || state === 'unsupported') {
        pushDot.style.background = '#ef4444';
        pushDot.style.boxShadow = 'none';
      } else {
        pushDot.style.background = '#f59e0b';
        pushDot.style.boxShadow = 'none';
      }
    }

    if (pushText) {
      pushText.textContent = label;
    }
  }

  toggleDrawer() {
    if (this.drawerOpen) {
      this.closeDrawer();
    } else {
      this.openDrawer();
    }
  }

  openDrawer() {
    const drawer = document.getElementById('notification-drawer');
    const backdrop = document.getElementById('notification-drawer-backdrop');
    if (drawer) {
      drawer.classList.add('open');
      drawer.style.transform = 'translateX(0%)';
      drawer.setAttribute('aria-hidden', 'false');
    }
    if (backdrop) {
      backdrop.classList.add('open');
      backdrop.style.display = 'block';
    }
    this.drawerOpen = true;
    this.loadNotifications();
  }

  closeDrawer() {
    const drawer = document.getElementById('notification-drawer');
    const backdrop = document.getElementById('notification-drawer-backdrop');
    if (drawer) {
      drawer.classList.remove('open');
      drawer.style.transform = 'translateX(100%)';
      drawer.setAttribute('aria-hidden', 'true');
    }
    if (backdrop) {
      backdrop.classList.remove('open');
      backdrop.style.display = 'none';
    }
    this.drawerOpen = false;
  }

  setFilter(category) {
    this.currentFilter = category;
    const filterPills = document.querySelectorAll('.notif-filter-pill');
    filterPills.forEach((pill) => {
      if ((pill.dataset.category || 'ALL') === category) {
        pill.classList.add('active');
      } else {
        pill.classList.remove('active');
      }
    });
    this.loadNotifications();
  }

  async loadNotifications() {
    const listContainer = document.getElementById('notification-list-items');
    if (!listContainer) return;

    listContainer.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:center; padding:32px; color:#64748b; font-size:0.8rem; gap:8px;">
        <span class="spinner" style="width:14px; height:14px; border:2px solid #38bdf8; border-top-color:transparent; border-radius:50%; animation:spin 0.8s linear infinite; display:inline-block;"></span>
        Loading alerts...
      </div>
    `;

    try {
      const url = `/api/notifications?category=${encodeURIComponent(this.currentFilter)}&page_size=40`;
      const resp = await fetch(url);
      if (!resp.ok) {
        throw new Error(`Status ${resp.status}`);
      }
      const data = await resp.json();
      this.renderNotificationList(data.items);
      this.updateUnreadBadge(data.unread_count);
    } catch (err) {
      console.error('[NotificationCenter] Error loading notifications:', err);
      listContainer.innerHTML = `
        <div style="padding:24px; text-align:center; color:#ef4444; font-size:0.75rem;">
          Failed to load alerts. (${err.message})
        </div>
      `;
    }
  }

  renderNotificationList(items) {
    const listContainer = document.getElementById('notification-list-items');
    if (!listContainer) return;

    if (!items || items.length === 0) {
      listContainer.innerHTML = `
        <div style="padding:48px 24px; text-align:center; color:#64748b;">
          <div style="font-size:1.8rem; margin-bottom:8px;">🔔</div>
          <div style="font-size:0.85rem; font-weight:600; color:#cbd5e1; margin-bottom:4px;">Zero Unread Alerts</div>
          <div style="font-size:0.75rem;">All systems and autonomous business pipelines are nominal.</div>
        </div>
      `;
      return;
    }

    let html = '';
    items.forEach((item) => {
      const isUnread = !item.is_read;
      const isCritical = item.priority === 'CRITICAL';
      const isHigh = item.priority === 'HIGH';

      let priorityColor = '#38bdf8';
      let priorityBg = 'rgba(56, 189, 248, 0.12)';
      if (isCritical) {
        priorityColor = '#ef4444';
        priorityBg = 'rgba(239, 68, 68, 0.15)';
      } else if (isHigh) {
        priorityColor = '#f59e0b';
        priorityBg = 'rgba(245, 158, 11, 0.12)';
      }

      const borderGlow = isCritical && isUnread 
        ? 'border: 1px solid rgba(239, 68, 68, 0.4); box-shadow: 0 0 12px rgba(239, 68, 68, 0.2);' 
        : (isUnread ? 'border: 1px solid rgba(56, 189, 248, 0.25);' : 'border: 1px solid rgba(255, 255, 255, 0.06);');

      html += `
        <div class="notification-card ${isUnread ? 'unread' : 'read'}" data-id="${item.id}" style="${borderGlow} background: ${isUnread ? '#0f141d' : '#0a0d13'}; border-radius:8px; padding:12px 14px; margin-bottom:10px; transition: all 0.2s ease;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; gap:8px;">
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              <span style="background:${priorityBg}; color:${priorityColor}; border:1px solid ${priorityColor}40; font-size:0.65rem; font-weight:700; padding:2px 6px; border-radius:4px; text-transform:uppercase;">
                ${item.severity || item.priority}
              </span>
              <span style="background:rgba(255,255,255,0.05); color:#94a3b8; font-size:0.65rem; font-weight:600; padding:2px 6px; border-radius:4px; text-transform:uppercase;">
                ${item.category}
              </span>
              ${isUnread ? '<span class="unread-dot" style="width:6px; height:6px; border-radius:50%; background:#38bdf8; display:inline-block;" title="Unread"></span>' : ''}
            </div>
            <span style="font-size:0.68rem; color:#64748b; white-space:nowrap;">
              ${formatRelativeTime(item.created_at)}
            </span>
          </div>

          <div style="font-size:0.84rem; font-weight:600; color:${isUnread ? '#f8fafc' : '#cbd5e1'}; margin-bottom:4px; line-height:1.3;">
            ${item.title}
          </div>

          <div style="font-size:0.75rem; color:#94a3b8; line-height:1.4; margin-bottom:10px; white-space:pre-line;">
            ${item.body}
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
            <div>
              ${item.deep_link ? `
                <button type="button" class="btn-notif-action" data-id="${item.id}" data-url="${item.deep_link}" style="display:inline-flex; align-items:center; gap:4px; font-size:0.72rem; font-weight:600; color:#38bdf8; text-decoration:none; padding:4px 9px; border-radius:4px; background:rgba(56,189,248,0.1); border:1px solid rgba(56,189,248,0.25); cursor:pointer;">
                  ${item.action_required ? 'Take Action →' : 'View Details →'}
                </button>
              ` : ''}
            </div>

            ${isUnread ? `
              <button type="button" class="btn-mark-single-read" data-id="${item.id}" style="background:transparent; border:none; color:#64748b; font-size:0.7rem; cursor:pointer; padding:3px 6px; border-radius:4px; display:inline-flex; align-items:center; gap:4px;">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                Mark Read
              </button>
            ` : ''}
          </div>
        </div>
      `;
    });

    listContainer.innerHTML = html;

    // Attach click listeners to cards and actions
    listContainer.querySelectorAll('.btn-notif-action').forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const notifId = btn.dataset.id;
        const targetUrl = btn.dataset.url;
        this.handleItemClick(notifId, targetUrl);
      };
    });

    listContainer.querySelectorAll('.btn-mark-single-read').forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const notifId = btn.dataset.id;
        this.markRead(notifId);
      };
    });
  }

  async handleItemClick(notificationId, deepLink) {
    await this.markRead(notificationId);
    this.closeDrawer();

    if (!deepLink) return;

    // Validate safe same-origin or relative path
    if (deepLink.startsWith('http://') || deepLink.startsWith('https://')) {
      const url = new URL(deepLink);
      if (url.origin !== window.location.origin) {
        console.warn('[NotificationCenter] External deep link blocked:', deepLink);
        return;
      }
    }

    // Parse target view from hash or query
    let targetView = null;
    if (deepLink.includes('#')) {
      const hashPart = deepLink.split('#')[1] || '';
      targetView = hashPart.split('?')[0];
    } else if (deepLink.includes('view=')) {
      const params = new URLSearchParams(deepLink.split('?')[1] || '');
      targetView = params.get('view');
    }

    if (targetView && typeof window.navToView === 'function') {
      window.navToView(targetView);
    } else if (deepLink && !deepLink.startsWith('#')) {
      window.location.href = deepLink;
    }
  }

  async markRead(notificationId) {
    try {
      const resp = await fetch(`/api/notifications/${notificationId}/read`, { method: 'POST' });
      if (resp.ok) {
        const card = document.querySelector(`.notification-card[data-id="${notificationId}"]`);
        if (card) {
          card.classList.remove('unread');
          card.classList.add('read');
          card.style.background = '#0a0d13';
          card.style.border = '1px solid rgba(255, 255, 255, 0.06)';
          card.style.boxShadow = 'none';
          const dot = card.querySelector('.unread-dot');
          if (dot) dot.remove();
          const btn = card.querySelector('.btn-mark-single-read');
          if (btn) btn.remove();
        }
        await this.fetchUnreadCount();
      }
    } catch (err) {
      console.error('[NotificationCenter] Failed to mark notification read:', err);
    }
  }

  async markAllRead() {
    try {
      const resp = await fetch('/api/notifications/read-all', { method: 'POST' });
      if (resp.ok) {
        this.updateUnreadBadge(0);
        const cards = document.querySelectorAll('.notification-card.unread');
        cards.forEach((card) => {
          card.classList.remove('unread');
          card.classList.add('read');
          card.style.background = '#0a0d13';
          card.style.border = '1px solid rgba(255, 255, 255, 0.06)';
          card.style.boxShadow = 'none';
          const dot = card.querySelector('.unread-dot');
          if (dot) dot.remove();
          const btn = card.querySelector('.btn-mark-single-read');
          if (btn) btn.remove();
        });
        this.showToast('All Alerts Read', 'All notifications marked as read.', 'info');
      }
    } catch (err) {
      console.error('[NotificationCenter] Failed to mark all read:', err);
    }
  }

  async fetchUnreadCount() {
    try {
      const resp = await fetch('/api/notifications/unread-count');
      if (resp.ok) {
        const data = await resp.json();
        this.updateUnreadBadge(data.unread_count || 0);
      }
    } catch (err) {
      // silent polling catch
    }
  }

  updateUnreadBadge(count) {
    this.unreadCount = count;
    const badge = document.getElementById('notif-badge');
    const bottomBadge = document.getElementById('mobile-bottom-notif-badge');
    const topCount = document.getElementById('drawer-unread-count');

    const updateBadge = (el) => {
      if (!el) return;
      if (count > 0) {
        el.textContent = count > 99 ? '99+' : String(count);
        el.style.display = 'inline-flex';
      } else {
        el.style.display = 'none';
      }
    };

    updateBadge(badge);
    updateBadge(bottomBadge);

    if (topCount) {
      topCount.textContent = `${count} unread`;
    }
  }

  async triggerTestEvent(eventType) {
    try {
      const resp = await fetch('/api/notifications/test-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: eventType }),
      });
      if (resp.ok) {
        const res = await resp.json();
        const title = res.notification ? res.notification.title : eventType;
        this.showToast('Test Alert Dispatched', title, 'info');
        await this.fetchUnreadCount();
        if (this.drawerOpen) {
          await this.loadNotifications();
        }
      } else {
        alert('Failed triggering test event.');
      }
    } catch (err) {
      alert(`Error triggering test: ${err.message}`);
    }
  }

  showToast(title, body, type = 'info') {
    let container = document.getElementById('toast-notification-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-notification-container';
      container.style.cssText = 'position:fixed; top:20px; right:20px; z-index:999999; display:flex; flex-direction:column; gap:10px; pointer-events:none;';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.cssText = `
      pointer-events:auto;
      background:#0f141d;
      border:1px solid ${type === 'critical' ? '#ef4444' : (type === 'success' ? '#10b981' : '#38bdf8')};
      box-shadow:0 8px 24px rgba(0,0,0,0.6);
      border-radius:8px;
      padding:12px 16px;
      color:#fff;
      font-size:0.8rem;
      min-width:280px;
      max-width:360px;
      animation:slideInRight 0.3s ease;
    `;

    toast.innerHTML = `
      <div style="font-weight:700; color:${type === 'critical' ? '#ef4444' : '#38bdf8'}; margin-bottom:4px;">${title}</div>
      <div style="color:#cbd5e1; font-size:0.75rem; line-height:1.3;">${body}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.4s ease';
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  }

  startPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollInterval = setInterval(() => {
      this.fetchUnreadCount();
      if (this.drawerOpen) {
        this.loadNotifications();
      }
    }, 20000);
  }
}

// Global initialization
function initNotificationCenter() {
  if (!window.notificationCenter) {
    window.notificationCenter = new NotificationCenterController();
    window.toggleNotificationCenter = () => window.notificationCenter.toggleDrawer();
  }
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', initNotificationCenter);
} else {
  initNotificationCenter();
}