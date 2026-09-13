/**
 * Service Worker for Agency OS CEO Mobile Notifications & PWA.
 * Scope: /
 * Intercepts push notifications, displays native mobile alerts,
 * and handles notification clicks with deep-linking into the dashboard.
 */

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function (event) {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (e) {
      payload = {
        title: "Agency OS Alert",
        body: event.data.text()
      };
    }
  } else {
    payload = {
      title: "Agency OS Alert",
      body: "New executive business event detected."
    };
  }

  const title = payload.title || "Agency OS Alert";
  const extraData = payload.data || {};
  const isCritical = extraData.priority === "CRITICAL";

  const options = {
    body: payload.body || "A new event requires your attention.",
    icon: payload.icon || "/static/icons/icon-192.png",
    badge: payload.badge || "/static/icons/badge-72.png",
    tag: payload.tag || ("agency-evt-" + (extraData.id || Date.now())),
    renotify: true,
    data: extraData,
    vibrate: isCritical ? [300, 100, 300, 100, 500] : [200, 100, 200],
    requireInteraction: isCritical,
    actions: [
      { action: "open", title: "View Alert" }
    ]
  };

  if (extraData.action_required) {
    options.actions.unshift({ action: "act", title: "Take Action" });
  }

  event.waitUntil(
    self.registration.showNotification(title, options).catch(function (err) {
      console.error("[ServiceWorker] showNotification failed:", err);
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();

  const data = event.notification.data || {};
  let targetUrl = data.deep_link || "/dashboard?tab=notifications";

  if (event.action === "act" && data.action_url) {
    targetUrl = data.action_url;
  }

  // Ensure target URL is relative or absolute on same origin
  if (!targetUrl.startsWith("/") && !targetUrl.startsWith(self.location.origin)) {
    targetUrl = "/dashboard?tab=notifications";
  }

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clientList) {
      // If a window is already open, focus it and notify client
      for (let i = 0; i < clientList.length; i++) {
        const client = clientList[i];
        if ("focus" in client) {
          client.postMessage({
            type: "AGENCY_NOTIFICATION_CLICK",
            targetUrl: targetUrl,
            data: data
          });
          if ("navigate" in client) {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      // If no window is open, open a new one
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
