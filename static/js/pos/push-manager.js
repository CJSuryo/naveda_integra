(function () {
    'use strict';

    async function getVapidKey() {
        const res = await fetch('/pos/push/vapid-key/');
        const data = await res.json();
        return data.public_key;
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = window.atob(base64);
        return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
    }

    async function subscribeToPush(role) {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') return;

        const registration = await navigator.serviceWorker.ready;
        const vapidKey = await getVapidKey();

        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey),
        });

        const sub = subscription.toJSON();
        await fetch('/pos/push/subscribe/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '',
            },
            body: JSON.stringify({
                endpoint: sub.endpoint,
                p256dh: sub.keys.p256dh,
                auth: sub.keys.auth,
                role: role,
            }),
        });
    }

    async function init(role) {
        if (!('serviceWorker' in navigator)) return;
        await navigator.serviceWorker.register('/static/js/pos/service-worker.js');
        await subscribeToPush(role);
    }

    window.PosNotifications = { init };
})();
