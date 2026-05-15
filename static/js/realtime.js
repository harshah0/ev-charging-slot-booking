(() => {
  const socketUrl = window.EV_CHARGE_SOCKET_URL || window.location.origin;
  const socket = window.io ? window.io(socketUrl, { transports: ["websocket", "polling"], withCredentials: true }) : null;

  const dom = {
    walletBalance: document.querySelector("[data-live-wallet-balance]"),
    adminMetrics: document.querySelectorAll("[data-live-metric]"),
    stationSlots: document.querySelectorAll("[data-live-station-slots]"),
    notifications: document.querySelector("[data-live-notification-list]"),
  };

  const chartInstances = window.EVChargeCharts || {};

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
    if (!payload.station_id) {
      return;
    }

    document.querySelectorAll(`[data-live-station-slots="${payload.station_id}"]`).forEach((element) => {
      const available = payload.available_slots ?? element.dataset.availableSlots ?? 0;
      const total = payload.total_slots ?? element.dataset.totalSlots ?? 0;
      element.textContent = `${available} / ${total}`;
      element.dataset.availableSlots = available;
      element.dataset.totalSlots = total;
    });
  };

  const updateWallet = (payload) => {
    if (!dom.walletBalance && !document.querySelector("[data-live-wallet-balance]")) {
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
  };

  const updateAdminCharts = (payload) => {
    if (!chartInstances.bookingsPerDay || !chartInstances.rechargeTrends || !chartInstances.statusDistribution || !chartInstances.topStations) {
      return;
    }

    if (Array.isArray(payload.bookings_per_day_labels) && Array.isArray(payload.bookings_per_day_counts)) {
      chartInstances.bookingsPerDay.data.labels = payload.bookings_per_day_labels;
      chartInstances.bookingsPerDay.data.datasets[0].data = payload.bookings_per_day_counts;
      chartInstances.bookingsPerDay.update();
    }

    if (Array.isArray(payload.recharge_labels) && Array.isArray(payload.recharge_values)) {
      chartInstances.rechargeTrends.data.labels = payload.recharge_labels;
      chartInstances.rechargeTrends.data.datasets[0].data = payload.recharge_values;
      chartInstances.rechargeTrends.update();
    }

    if (Array.isArray(payload.status_labels) && Array.isArray(payload.status_counts)) {
      chartInstances.statusDistribution.data.labels = payload.status_labels;
      chartInstances.statusDistribution.data.datasets[0].data = payload.status_counts;
      chartInstances.statusDistribution.update();
    }

    if (Array.isArray(payload.top_stations) && Array.isArray(payload.top_station_counts)) {
      chartInstances.topStations.data.labels = payload.top_stations;
      chartInstances.topStations.data.datasets[0].data = payload.top_station_counts;
      chartInstances.topStations.update();
    }
  };

  const updateAdminMetrics = (payload) => {
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
    document.body.classList.add("socket-connected");
  });

  socket.on("disconnect", () => {
    document.body.classList.remove("socket-connected");
  });

  socket.on("socket:ready", (payload) => {
    if (payload?.server_time) {
      document.documentElement.dataset.serverTime = payload.server_time;
    }
  });

  socket.on("booking:update", (payload) => {
    updateStationSlots(payload);
    updateBookingCountdowns(payload);
    appendNotification(payload);
  });

  socket.on("station:update", updateStationSlots);
  socket.on("wallet:update", (payload) => {
    updateWallet(payload);
    appendNotification(payload);
  });
  socket.on("analytics:update", (payload) => {
    updateAdminMetrics(payload);
    updateAdminCharts(payload);
    appendNotification(payload);
  });
  socket.on("notification:new", appendNotification);
})();
