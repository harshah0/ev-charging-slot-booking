(() => {
  const socketUrl = window.EV_CHARGE_SOCKET_URL || window.location.origin;
  const socket = window.io
    ? window.io(socketUrl, {
        path: "/socket.io",
        transports: ["websocket", "polling"],
        upgrade: true,
        rememberUpgrade: true,
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 10000,
        randomizationFactor: 0.5,
        timeout: 20000,
      })
    : null;

  const state = {
    pendingAnalytics: null,
    reconnectSyncRequested: false,
  };

  const dom = {
    walletBalance: document.querySelector("[data-live-wallet-balance]"),
    adminMetrics: document.querySelectorAll("[data-live-metric]"),
    stationSlots: document.querySelectorAll("[data-live-station-slots]"),
    notifications: document.querySelector("[data-live-notification-list]"),
  };

  const getChartInstances = () => window.EVChargeCharts || {};

  const debugRealtime = (eventName, payload) => {
    try {
      console.debug(`[realtime] ${eventName}`, payload ?? {});
    } catch (error) {
      // console.debug can be unavailable in older embedded clients
    }
  };

  const broadcastRealtimeEvent = (eventName, detail) => {
    try {
      window.dispatchEvent(new CustomEvent(eventName, { detail }));
    } catch (error) {
      // Ignore environments that block CustomEvent construction.
    }
  };

  const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

  const requestSync = (reason) => {
    if (!socket) {
      return;
    }
    state.reconnectSyncRequested = true;
    debugRealtime("emit sync:request", { reason });
    socket.emit("sync:request", { reason });
  };

  window.EVChargeRealtime = window.EVChargeRealtime || {};
  window.EVChargeRealtime.requestSync = requestSync;
  window.EVChargeRealtime.flushPendingState = () => {
    if (state.pendingAnalytics) {
      debugRealtime("apply pending analytics:update", state.pendingAnalytics);
      updateAdminMetrics(state.pendingAnalytics);
      updateAdminCharts(state.pendingAnalytics);
    }
  };

  const formatCurrency = (value) => {
    const amount = Number(value || 0);
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(amount);
  };

  const formatInteger = (value) => new Intl.NumberFormat("en-IN").format(Number(value || 0));

  const setText = (selector, value, formatter = String) => {
    document.querySelectorAll(selector).forEach((element) => {
      element.textContent = formatter(value);
    });
  };

  const updateMetric = (name, value, formatter = String) => {
    document.querySelectorAll(`[data-live-metric="${name}"]`).forEach((element) => {
      element.textContent = formatter(value);
    });
  };

  const appendNotification = (payload) => {
    if (!dom.notifications) {
      return;
    }

    if (!isObject(payload)) {
      debugRealtime("drop invalid notification payload", payload);
      return;
    }

    const message = payload.message || payload.action || "Update received";
    const item = document.createElement("div");
    item.className = "realtime-notification";
    item.innerHTML = `
      <div class="d-flex justify-content-between align-items-start gap-3">
        <div>
          <div class="fw-semibold text-white">Live update</div>
          <div class="text-white-50 small">${message}</div>
        </div>
        <span class="badge text-bg-light text-uppercase">${payload.action || "update"}</span>
      </div>
    `;
    dom.notifications.prepend(item);
    while (dom.notifications.children.length > 5) {
      dom.notifications.lastElementChild?.remove();
    }
  };

  const updateStationSlots = (payload) => {
    if (!isObject(payload)) {
      debugRealtime("drop invalid station payload", payload);
      return;
    }

    const stationId = payload.station_id ?? payload.id;
    if (!stationId) {
      return;
    }

    document.querySelectorAll(`[data-live-station-slots="${stationId}"]`).forEach((element) => {
      const available = payload.available_slots ?? element.dataset.availableSlots ?? 0;
      const total = payload.total_slots ?? element.dataset.totalSlots ?? 0;
      const hadSlotsSuffix = /\bslots\b/i.test(element.textContent);
      element.textContent = hadSlotsSuffix ? `${available} / ${total} slots` : `${available} / ${total}`;
      element.dataset.availableSlots = available;
      element.dataset.totalSlots = total;
    });
  };

  const applyStationBulkUpdate = (payload) => {
    if (!isObject(payload) || !Array.isArray(payload.stations)) {
      debugRealtime("drop invalid station:bulk_update payload", payload);
      return;
    }
    debugRealtime("receive station:bulk_update", { stationCount: payload.stations.length });
    payload.stations.forEach((station) => updateStationSlots(station));
    broadcastRealtimeEvent("evcharge:station-bulk-update", payload);
  };

  const updateWallet = (payload) => {
    if (!dom.walletBalance && !document.querySelector("[data-live-wallet-balance]")) {
      return;
    }

    if (!isObject(payload)) {
      debugRealtime("drop invalid wallet payload", payload);
      return;
    }

    const value = payload.wallet_balance ?? payload.balance_after;
    setText("[data-live-wallet-balance]", value, formatCurrency);
    if (window.EVChargeBookingState && typeof value !== "undefined") {
      window.EVChargeBookingState.currentBalance = Number(value || 0);
    }
    if (window.EVChargeRechargeState && typeof value !== "undefined") {
      window.EVChargeRechargeState.currentBalance = Number(value || 0);
    }
    if (typeof window.EVChargeBookingPreview === "function") {
      window.EVChargeBookingPreview();
    }
    if (typeof window.EVChargeRechargePreview === "function") {
      window.EVChargeRechargePreview();
    }
    broadcastRealtimeEvent("evcharge:wallet-update", payload);
  };

  const updateAdminCharts = (payload) => {
    const chartInstances = getChartInstances();
    if (!isObject(payload)) {
      debugRealtime("drop invalid analytics payload", payload);
      return;
    }

    if (!chartInstances.bookingsPerDay || !chartInstances.rechargeTrends || !chartInstances.statusDistribution || !chartInstances.topStations) {
      state.pendingAnalytics = payload;
      debugRealtime("queue analytics:update until charts ready", payload);
      return;
    }

    state.pendingAnalytics = null;
    broadcastRealtimeEvent("evcharge:analytics-update", payload);

    if (chartInstances.bookingsPerDay && Array.isArray(payload.bookings_per_day_labels) && Array.isArray(payload.bookings_per_day_counts)) {
      chartInstances.bookingsPerDay.data.labels = payload.bookings_per_day_labels;
      chartInstances.bookingsPerDay.data.datasets[0].data = payload.bookings_per_day_counts;
      chartInstances.bookingsPerDay.update();
    }

    if (chartInstances.rechargeTrends && Array.isArray(payload.recharge_labels) && Array.isArray(payload.recharge_values)) {
      chartInstances.rechargeTrends.data.labels = payload.recharge_labels;
      chartInstances.rechargeTrends.data.datasets[0].data = payload.recharge_values;
      chartInstances.rechargeTrends.update();
    }

    if (chartInstances.statusDistribution && Array.isArray(payload.status_labels) && Array.isArray(payload.status_counts)) {
      chartInstances.statusDistribution.data.labels = payload.status_labels;
      chartInstances.statusDistribution.data.datasets[0].data = payload.status_counts;
      chartInstances.statusDistribution.update();
    }

    if (chartInstances.topStations && Array.isArray(payload.top_stations) && Array.isArray(payload.top_station_counts)) {
      chartInstances.topStations.data.labels = payload.top_stations;
      chartInstances.topStations.data.datasets[0].data = payload.top_station_counts;
      chartInstances.topStations.update();
    }
  };

  const updateAdminMetrics = (payload) => {
    if (!isObject(payload)) {
      debugRealtime("drop invalid admin metrics payload", payload);
      return;
    }

    updateMetric("total_users", payload.total_users, formatInteger);
    updateMetric("total_stations", payload.total_stations, formatInteger);
    updateMetric("total_bookings", payload.total_bookings, formatInteger);
    updateMetric("active_bookings", payload.active_bookings, formatInteger);
    updateMetric("completed_bookings", payload.completed_bookings, formatInteger);
    updateMetric("expired_bookings", payload.expired_bookings, formatInteger);
    updateMetric("cancelled_bookings", payload.cancelled_bookings, formatInteger);
    updateMetric("occupied_slots", payload.occupied_slots, formatInteger);
    updateMetric("available_slots", payload.available_slots, formatInteger);
    updateMetric("slot_utilization", payload.slot_utilization, (value) => `${Number(value || 0).toFixed(1)}%`);
    updateMetric("total_wallet_revenue", payload.total_wallet_revenue, formatCurrency);

    const utilizationBar = document.querySelector("[data-live-slot-utilization-bar]");
    if (utilizationBar && typeof payload.slot_utilization !== "undefined") {
      utilizationBar.style.width = `${Number(payload.slot_utilization || 0).toFixed(1)}%`;
      utilizationBar.setAttribute("aria-valuenow", String(payload.slot_utilization || 0));
    }
  };

  const updateBookingCountdowns = (payload) => {
    if (!isObject(payload)) {
      return;
    }
    document.querySelectorAll("[data-live-booking-expiry]").forEach((element) => {
      if (payload.booking && String(element.dataset.bookingId) === String(payload.booking.id)) {
        element.textContent = payload.booking.expires_at ? new Date(payload.booking.expires_at).toLocaleString() : "Expired";
      }
    });
  };

  if (!socket) {
    return;
  }

  socket.on("connect", () => {
    debugRealtime("connect", { id: socket.id, transport: socket.io.engine?.transport?.name });
    document.body.classList.add("socket-connected");
    requestSync("connect");
  });

  socket.on("disconnect", () => {
    debugRealtime("disconnect", { id: socket.id });
    document.body.classList.remove("socket-connected");
  });

  socket.on("connect_error", (error) => {
    debugRealtime("connect_error", { message: error?.message, description: error?.description });
    document.body.classList.remove("socket-connected");
  });

  socket.io.on("reconnect_attempt", (attempt) => {
    debugRealtime("reconnect_attempt", { attempt });
  });

  socket.io.on("reconnect_error", (error) => {
    debugRealtime("reconnect_error", { message: error?.message });
  });

  socket.io.on("reconnect_failed", () => {
    debugRealtime("reconnect_failed");
  });

  socket.io.on("reconnect", (attempt) => {
    debugRealtime("reconnect", { attempt });
    requestSync("reconnect");
  });

  socket.on("socket:ready", (payload) => {
    debugRealtime("socket:ready", payload);
    if (payload?.server_time) {
      document.documentElement.dataset.serverTime = payload.server_time;
    }
  });

  socket.on("booking:update", (payload) => {
    debugRealtime("receive booking:update", payload);
    updateStationSlots(payload);
    updateBookingCountdowns(payload);
    appendNotification(payload);
    broadcastRealtimeEvent("evcharge:booking-update", payload);
  });

  socket.on("station:update", (payload) => {
    debugRealtime("receive station:update", payload);
    updateStationSlots(payload);
    broadcastRealtimeEvent("evcharge:station-update", payload);
  });
  socket.on("station:bulk_update", applyStationBulkUpdate);
  socket.on("wallet:update", (payload) => {
    debugRealtime("receive wallet:update", payload);
    updateWallet(payload);
    appendNotification(payload);
  });
  socket.on("analytics:update", (payload) => {
    debugRealtime("receive analytics:update", payload);
    updateAdminMetrics(payload);
    updateAdminCharts(payload);
    appendNotification(payload);
  });
  socket.on("notification:new", (payload) => {
    debugRealtime("receive notification:new", payload);
    appendNotification(payload);
  });
})();
