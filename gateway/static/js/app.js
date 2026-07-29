/**
 * Tunnel Gateway — Admin Dashboard Controller
 * 
 * Handles API key authentication with localStorage persistence, real-time
 * telemetry polling (2s interval), runtime settings management, and active
 * tunnel operations.
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- State Variables ---
    let apiKey = localStorage.getItem("tunnel_api_key") || null;
    let pollInterval = null;
    let isPolling = localStorage.getItem("tunnel_auto_refresh") !== "false";
    let currentTheme = localStorage.getItem("tunnel_theme") || "light";

    // --- DOM Elements ---
    const authBtn = document.getElementById("auth-btn");
    const authBtnText = document.getElementById("auth-btn-text");
    const authStatusDot = document.getElementById("auth-status-indicator");
    const authModal = document.getElementById("auth-modal");
    const closeModalBtn = document.getElementById("close-modal-btn");
    const cancelModalBtn = document.getElementById("cancel-modal-btn");
    const saveKeyBtn = document.getElementById("save-key-btn");
    const clearKeyBtn = document.getElementById("clear-key-btn");
    const modalInputApiKey = document.getElementById("modal-input-apikey");
    const toggleKeyVisibilityBtn = document.getElementById("toggle-key-visibility-btn");
    const modalAuthFeedback = document.getElementById("modal-auth-feedback");

    const mobileMenuBtn = document.getElementById("mobile-menu-btn");
    const mobileMenuCloseBtn = document.getElementById("mobile-menu-close-btn");
    const headerControls = document.getElementById("header-controls");
    const mobileMenuBackdrop = document.getElementById("mobile-menu-backdrop");

    const themeToggleBtn = document.getElementById("theme-toggle-btn");
    const themeIcon = document.getElementById("theme-icon");
    const themeText = document.getElementById("theme-text");

    const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    const lastUpdatedTimestamp = document.getElementById("last-updated-timestamp");

    const statusBadgeContainer = document.getElementById("status-badge-container");
    const serverStatusText = document.getElementById("server-status-text");
    const serverUptimeText = document.getElementById("server-uptime");

    // Metrics DOM
    const statTotalRequests = document.getElementById("stat-total-requests");
    const statActiveRequests = document.getElementById("stat-active-requests");
    const statAvgLatency = document.getElementById("stat-avg-latency");
    const statTotalBytes = document.getElementById("stat-total-bytes");
    const statBytesUp = document.getElementById("stat-bytes-up");
    const statBytesDown = document.getElementById("stat-bytes-down");
    const statCpu = document.getElementById("stat-cpu");
    const barCpu = document.getElementById("bar-cpu");
    const statMemory = document.getElementById("stat-memory");
    const statMemoryBytes = document.getElementById("stat-memory-bytes");
    const statThreads = document.getElementById("stat-threads");
    const statProcessId = document.getElementById("stat-process-id");

    // Tunnels Table DOM
    const tunnelsTbody = document.getElementById("tunnels-tbody");
    const tunnelsEmptyState = document.getElementById("tunnels-empty-state");
    const tunnelsCountBadge = document.getElementById("tunnels-count-badge");
    const refreshTunnelsBtn = document.getElementById("refresh-tunnels-btn");

    // Settings DOM
    const settingsForm = document.getElementById("settings-form");
    const settingsUnauthOverlay = document.getElementById("settings-unauth-overlay");
    const overlayAuthBtn = document.getElementById("overlay-auth-btn");
    const reloadSettingsBtn = document.getElementById("reload-settings-btn");
    const resetStatsBtn = document.getElementById("reset-stats-btn");

    // Tunnels Auth Overlay DOM
    const tunnelsUnauthOverlay = document.getElementById("tunnels-unauth-overlay");
    const overlayTunnelsAuthBtn = document.getElementById("overlay-tunnels-auth-btn");

    // Dummy Keys DOM
    const keysUnauthOverlay = document.getElementById("keys-unauth-overlay");
    const overlayKeysAuthBtn = document.getElementById("overlay-keys-auth-btn");
    const dummyKeysTbody = document.getElementById("dummy-keys-tbody");
    const dummyKeysEmptyState = document.getElementById("dummy-keys-empty-state");
    const createDummyKeyBtn = document.getElementById("create-dummy-key-btn");
    const inputCustomDummyKey = document.getElementById("input-custom-dummy-key");
    const refreshKeysBtn = document.getElementById("refresh-keys-btn");

    // Server Info DOM
    const infoVersion = document.getElementById("info-version");
    const infoProtocol = document.getElementById("info-protocol");
    const infoOs = document.getElementById("info-os");
    const infoHostname = document.getElementById("info-hostname");
    const infoPython = document.getElementById("info-python");

    // =========================================================================
    // Initialization & Auth State
    // =========================================================================

    function updateAuthStateUI() {
        if (apiKey) {
            authBtnText.textContent = "Authenticated";
            authStatusDot.classList.remove("unauth");
            authStatusDot.classList.add("auth");
            clearKeyBtn.classList.remove("hidden");
            settingsUnauthOverlay.classList.add("hidden");
            if (tunnelsUnauthOverlay) tunnelsUnauthOverlay.classList.add("hidden");
            if (keysUnauthOverlay) keysUnauthOverlay.classList.add("hidden");
            fetchDummyKeys();
        } else {
            authBtnText.textContent = "Authenticate";
            authStatusDot.classList.remove("auth");
            authStatusDot.classList.add("unauth");
            clearKeyBtn.classList.add("hidden");
            settingsUnauthOverlay.classList.remove("hidden");
            if (tunnelsUnauthOverlay) tunnelsUnauthOverlay.classList.remove("hidden");
            if (keysUnauthOverlay) keysUnauthOverlay.classList.remove("hidden");
        }
    }

    function applyTheme(theme) {
        if (theme === "dark") {
            document.documentElement.classList.add("dark");
            if (themeIcon) themeIcon.className = "bi bi-sun-fill";
            if (themeText) themeText.textContent = "Light Mode";
        } else {
            document.documentElement.classList.remove("dark");
            if (themeIcon) themeIcon.className = "bi bi-moon-fill";
            if (themeText) themeText.textContent = "Dark Mode";
        }
    }

    function toggleMobileMenu(forceClose = false) {
        if (!headerControls) return;
        const isOpen = headerControls.classList.contains("open");
        if (isOpen || forceClose) {
            headerControls.classList.remove("open");
            if(mobileMenuBackdrop) mobileMenuBackdrop.classList.remove("open");
            document.body.classList.remove("menu-open");
        } else {
            headerControls.classList.add("open");
            if(mobileMenuBackdrop) mobileMenuBackdrop.classList.add("open");
            document.body.classList.add("menu-open");
        }
    }

    function init() {
        applyTheme(currentTheme);
        updateAuthStateUI();
        fetchInfo();
        fetchStatusAndHealth();

        if (apiKey) {
            verifySavedApiKey(apiKey);
        }

        // Start 2s polling
        if (autoRefreshToggle) {
            autoRefreshToggle.checked = isPolling;
        }
        
        if (isPolling) {
            startPolling();
        }
    }

    // =========================================================================
    // Polling & Telemetry Fetching
    // =========================================================================

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(() => {
            if (isPolling) {
                fetchStatusAndHealth();
            }
        }, 2000);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    async function fetchStatusAndHealth() {
        try {
            const headers = apiKey ? { "X-API-Key": apiKey } : {};
            const [statusRes, healthRes] = await Promise.all([
                fetch("/admin/status", { headers }),
                fetch("/admin/health", { headers })
            ]);

            if (statusRes.ok) {
                const statusData = await statusRes.json();
                renderStatus(statusData);
            } else {
                renderOffline();
            }

            if (healthRes.ok) {
                const healthData = await healthRes.json();
                renderHealth(healthData);
            }
        } catch (error) {
            renderOffline();
        }
    }

    async function fetchInfo() {
        try {
            const res = await fetch("/admin/info");
            if (res.ok) {
                const data = await res.json();
                infoVersion.textContent = `v${data.server_version}`;
                infoProtocol.textContent = `v${data.protocol_version}`;
                infoOs.textContent = data.operating_system || "Unknown OS";
                infoHostname.textContent = data.hostname || "localhost";
                infoPython.textContent = (data.python_version || "").split(" ")[0] || "Python 3";
            }
        } catch (error) {
            console.error("Failed to fetch server info:", error);
        }
    }

    async function fetchSettings() {
        if (!apiKey) return;
        try {
            const res = await fetch("/admin/settings", {
                headers: { "X-API-Key": apiKey }
            });
            if (res.ok) {
                const data = await res.json();
                populateSettingsForm(data);
            } else if (res.status === 401) {
                handleAuthFailure("Your saved API key was rejected by the server.");
            }
        } catch (error) {
            console.error("Failed to load settings:", error);
        }
    }

    // =========================================================================
    // Rendering Helpers
    // =========================================================================

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    function formatUptime(seconds) {
        if (!seconds || seconds < 0) return "0s";
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) return `${h}h ${m}m`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function renderOffline() {
        statusBadgeContainer.classList.remove("online");
        statusBadgeContainer.classList.add("offline");
        serverStatusText.textContent = "Offline";
        serverUptimeText.textContent = "Disconnected";
    }

    function renderStatus(data) {
        statusBadgeContainer.classList.remove("offline");
        statusBadgeContainer.classList.add("online");
        serverStatusText.textContent = "Online";
        serverUptimeText.textContent = formatUptime(data.uptime_seconds);

        lastUpdatedTimestamp.textContent = `Updated ${new Date().toLocaleTimeString()}`;

        // Request Stats
        statTotalRequests.textContent = (data.total_requests || 0).toLocaleString();
        statActiveRequests.textContent = `${data.active_requests || 0} currently active`;
        statAvgLatency.textContent = (data.average_latency_ms || 0).toFixed(2);

        // Byte Transfer
        statTotalBytes.textContent = formatBytes(data.total_bytes_transferred || 0);
        statBytesUp.textContent = formatBytes(data.bytes_uploaded || 0);
        statBytesDown.textContent = formatBytes(data.bytes_downloaded || 0);

        // Tunnels Table
        renderTunnelsTable(data.tunnels || []);
    }

    function renderHealth(data) {
        // CPU
        const cpuPercent = (data.cpu_usage_percent || 0).toFixed(1);
        statCpu.textContent = cpuPercent;
        barCpu.style.width = `${Math.min(100, Math.max(0, cpuPercent))}%`;

        // Memory
        const memPercent = (data.memory_usage_percent || 0).toFixed(1);
        statMemory.textContent = memPercent;
        const usedMb = ((data.used_memory_bytes || 0) / (1024 * 1024)).toFixed(0);
        const totalMb = ((data.total_memory_bytes || 0) / (1024 * 1024)).toFixed(0);
        statMemoryBytes.textContent = `${usedMb} MB / ${totalMb} MB`;

        // Threads & Process
        statThreads.textContent = data.thread_count || 0;
        statProcessId.textContent = `PID: ${data.process_id || 0}`;
    }

    function renderTunnelsTable(tunnels) {
        if (!apiKey) {
            tunnelsCountBadge.textContent = "🔒 Hidden (Auth Required)";
        } else {
            tunnelsCountBadge.textContent = `${tunnels.length} connected`;
        }
        tunnelsTbody.innerHTML = "";

        if (tunnels.length === 0) {
            tunnelsEmptyState.classList.remove("hidden");
            return;
        }

        tunnelsEmptyState.classList.add("hidden");

        tunnels.forEach(tunnel => {
            const tr = document.createElement("tr");

            const uptimeStr = formatUptime(tunnel.uptime_seconds || 0);
            const path = tunnel.target_path || "/";

            tr.innerHTML = `
                <td class="path-cell" data-label="Target Path"><span class="path-badge"><i class="bi bi-link-45deg"></i> ${path}</span></td>
                <td class="ip-cell" data-label="Client IP">${tunnel.client_ip || "Unknown"}</td>
                <td class="bytes-cell" data-label="Requests Served">${(tunnel.requests_served || 0).toLocaleString()}</td>
                <td class="bytes-cell" data-label="Data Uploaded">${formatBytes(tunnel.bytes_uploaded || 0)}</td>
                <td class="bytes-cell" data-label="Data Downloaded">${formatBytes(tunnel.bytes_downloaded || 0)}</td>
                <td class="time-cell" data-label="Connected Since">${uptimeStr} ago</td>
                <td class="text-right" data-label="Actions">
                    <div class="tunnel-actions">
                        <a href="${path}" target="_blank" rel="noopener" class="btn btn-primary btn-sm visit-tunnel-btn" title="Open ${path} in new tab">
                            <i class="bi bi-box-arrow-up-right"></i> Visit
                        </a>
                        <button class="btn btn-danger-outline btn-sm disconnect-tunnel-btn" data-path="${path}" title="Disconnect Tunnel">
                            <i class="bi bi-x-circle-fill"></i> Disconnect
                        </button>
                    </div>
                </td>
            `;

            tunnelsTbody.appendChild(tr);
        });

        // Attach click events for disconnect buttons
        document.querySelectorAll(".disconnect-tunnel-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const path = e.currentTarget.getAttribute("data-path");
                if (confirm(`Are you sure you want to terminate the tunnel at ${path}?`)) {
                    await disconnectTunnel(path);
                }
            });
        });
    }

    function populateSettingsForm(data) {
        if (data.streaming_threshold_bytes !== undefined) {
            document.getElementById("input-streaming-threshold").value = data.streaming_threshold_bytes;
        }
        if (data.chunk_size !== undefined) {
            document.getElementById("input-chunk-size").value = data.chunk_size;
        }
        if (data.tunnel_timeout !== undefined) {
            document.getElementById("input-tunnel-timeout").value = data.tunnel_timeout;
        }
        if (data.ping_interval !== undefined) {
            document.getElementById("input-ping-interval").value = data.ping_interval;
        }
        if (data.ping_timeout !== undefined) {
            document.getElementById("input-ping-timeout").value = data.ping_timeout;
        }
        if (data.rate_limit_default !== undefined) {
            document.getElementById("input-rate-limit").value = data.rate_limit_default;
        }
    }

    // =========================================================================
    // API Actions & Auth Handlers
    // =========================================================================

    async function verifySavedApiKey(keyToVerify) {
        try {
            const res = await fetch("/admin/verify", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": keyToVerify
                },
                body: JSON.stringify({ api_key: keyToVerify })
            });

            if (res.ok) {
                apiKey = keyToVerify;
                localStorage.setItem("tunnel_api_key", apiKey);
                updateAuthStateUI();
                fetchSettings();
            } else {
                handleAuthFailure("Saved API key is invalid or expired.");
            }
        } catch (error) {
            console.error("Verification error:", error);
        }
    }

    function handleAuthFailure(msg) {
        apiKey = null;
        localStorage.removeItem("tunnel_api_key");
        updateAuthStateUI();
        if (msg) showToast(msg, "error");
    }

    async function disconnectTunnel(path) {
        if (!apiKey) {
            showToast("Authentication required to disconnect tunnels.", "error");
            openAuthModal();
            return;
        }

        try {
            const res = await fetch(`/admin/tunnels?path=${encodeURIComponent(path)}`, {
                method: "DELETE",
                headers: { "X-API-Key": apiKey }
            });

            const data = await res.json();
            if (res.ok) {
                showToast(`Tunnel ${path} disconnected successfully.`, "success");
                fetchStatusAndHealth();
            } else if (res.status === 401) {
                handleAuthFailure("API key unauthorized.");
                openAuthModal();
            } else {
                showToast(data.error || "Failed to disconnect tunnel.", "error");
            }
        } catch (error) {
            showToast("Network error while disconnecting tunnel.", "error");
        }
    }

    // =========================================================================
    // Event Listeners & Modals
    // =========================================================================

    function openAuthModal() {
        if (apiKey) modalInputApiKey.value = apiKey;
        modalAuthFeedback.classList.add("hidden");
        authModal.classList.remove("hidden");
        modalInputApiKey.focus();
    }

    function closeAuthModal() {
        authModal.classList.add("hidden");
    }

    authBtn.addEventListener("click", () => {
        toggleMobileMenu(true);
        openAuthModal();
    });
    overlayAuthBtn.addEventListener("click", openAuthModal);
    if (overlayTunnelsAuthBtn) overlayTunnelsAuthBtn.addEventListener("click", openAuthModal);
    if (overlayKeysAuthBtn) overlayKeysAuthBtn.addEventListener("click", openAuthModal);
    closeModalBtn.addEventListener("click", closeAuthModal);
    cancelModalBtn.addEventListener("click", closeAuthModal);

    if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", () => toggleMobileMenu(false));
    if (mobileMenuCloseBtn) mobileMenuCloseBtn.addEventListener("click", () => toggleMobileMenu(true));
    if (mobileMenuBackdrop) mobileMenuBackdrop.addEventListener("click", () => toggleMobileMenu(true));

    if (createDummyKeyBtn) createDummyKeyBtn.addEventListener("click", createDummyKey);
    if (refreshKeysBtn) refreshKeysBtn.addEventListener("click", () => {
        fetchDummyKeys();
        showToast("Refreshed shared API keys list.", "info");
    });

    toggleKeyVisibilityBtn.addEventListener("click", () => {
        const type = modalInputApiKey.getAttribute("type") === "password" ? "text" : "password";
        modalInputApiKey.setAttribute("type", type);
        toggleKeyVisibilityBtn.innerHTML = type === "password" ? '<i class="bi bi-eye"></i>' : '<i class="bi bi-eye-slash"></i>';
    });

    saveKeyBtn.addEventListener("click", async () => {
        const inputVal = modalInputApiKey.value.trim();
        if (!inputVal) {
            showModalFeedback("Please enter an API key.", "error");
            return;
        }

        saveKeyBtn.disabled = true;
        saveKeyBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Verifying...';

        try {
            const res = await fetch("/admin/verify", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": inputVal
                },
                body: JSON.stringify({ api_key: inputVal })
            });

            const data = await res.json();
            if (res.ok) {
                apiKey = inputVal;
                localStorage.setItem("tunnel_api_key", apiKey);
                updateAuthStateUI();
                showToast("API key authenticated and saved in browser!", "success");
                fetchSettings();
                closeAuthModal();
            } else {
                showModalFeedback(data.error || "Invalid API key provided.", "error");
            }
        } catch (error) {
            showModalFeedback("Network error during verification.", "error");
        } finally {
            saveKeyBtn.disabled = false;
            saveKeyBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Save & Verify';
        }
    });

    clearKeyBtn.addEventListener("click", () => {
        apiKey = null;
        localStorage.removeItem("tunnel_api_key");
        modalInputApiKey.value = "";
        updateAuthStateUI();
        showToast("API key removed from browser storage.", "info");
        closeAuthModal();
    });

    function showModalFeedback(msg, type) {
        modalAuthFeedback.textContent = msg;
        modalAuthFeedback.className = `auth-feedback ${type}`;
    }

    // Settings Form Submission
    settingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!apiKey) {
            showToast("You must authenticate with your API key to save settings.", "error");
            openAuthModal();
            return;
        }

        const formData = new FormData(settingsForm);
        const payload = Object.fromEntries(formData.entries());

        const saveBtn = document.getElementById("save-settings-btn");
        const origText = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';

        try {
            const res = await fetch("/admin/settings", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": apiKey
                },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok) {
                showToast("Runtime configuration updated successfully!", "success");
                if (data.settings) populateSettingsForm(data.settings);
            } else if (res.status === 401) {
                handleAuthFailure("API key unauthorized.");
                openAuthModal();
            } else {
                showToast(data.error || "Failed to save settings.", "error");
            }
        } catch (error) {
            showToast("Network error while saving configuration.", "error");
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = origText;
        }
    });

    reloadSettingsBtn.addEventListener("click", () => {
        fetchSettings();
        showToast("Settings reloaded from server.", "info");
    });

    resetStatsBtn.addEventListener("click", async () => {
        if (!apiKey) {
            showToast("Authentication required to reset telemetry statistics.", "error");
            openAuthModal();
            return;
        }

        if (!confirm("Are you sure you want to reset all server request counters and bytes transferred?")) {
            return;
        }

        try {
            const res = await fetch("/admin/stats/reset", {
                method: "POST",
                headers: { "X-API-Key": apiKey }
            });

            if (res.ok) {
                showToast("Server telemetry counters reset successfully.", "success");
                fetchStatusAndHealth();
            } else if (res.status === 401) {
                handleAuthFailure("API key unauthorized.");
                openAuthModal();
            } else {
                showToast("Failed to reset statistics.", "error");
            }
        } catch (error) {
            showToast("Network error during reset.", "error");
        }
    });

    autoRefreshToggle.addEventListener("change", (e) => {
        isPolling = e.target.checked;
        localStorage.setItem("tunnel_auto_refresh", isPolling);
        if (isPolling) {
            startPolling();
            showToast("Auto-refresh enabled (2s interval).", "info");
        } else {
            stopPolling();
            showToast("Auto-refresh paused.", "info");
        }
    });

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            currentTheme = currentTheme === "light" ? "dark" : "light";
            localStorage.setItem("tunnel_theme", currentTheme);
            applyTheme(currentTheme);
        });
    }

    refreshTunnelsBtn.addEventListener("click", () => {
        fetchStatusAndHealth();
        showToast("Refreshed active tunnels list.", "info");
    });

    // =========================================================================
    // Toast Notifications System
    // =========================================================================

    function showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;

        let iconClass = "bi-info-circle-fill";
        if (type === "success") iconClass = "bi-check-circle-fill";
        if (type === "error") iconClass = "bi-exclamation-triangle-fill";

        toast.innerHTML = `
            <i class="bi ${iconClass}"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 300);
        }, 4000);
    }

    // =========================================================================
    // Dummy / Shared API Keys Management
    // =========================================================================

    async function fetchDummyKeys() {
        if (!apiKey) return;
        try {
            const res = await fetch("/admin/keys", {
                headers: { "X-API-Key": apiKey }
            });
            if (res.ok) {
                const data = await res.json();
                renderDummyKeysTable(data.dummy_keys || []);
            }
        } catch (error) {
            console.error("Failed to load dummy keys:", error);
        }
    }

    function renderDummyKeysTable(keys) {
        if (!dummyKeysTbody) return;
        dummyKeysTbody.innerHTML = "";
        if (keys.length === 0) {
            if (dummyKeysEmptyState) dummyKeysEmptyState.classList.remove("hidden");
            return;
        }
        if (dummyKeysEmptyState) dummyKeysEmptyState.classList.add("hidden");
        keys.forEach(keyStr => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="path-cell" data-label="Shared Key"><span class="path-badge" style="background: var(--accent-purple-subtle); color: var(--accent-purple);"><i class="bi bi-key-fill"></i> ${keyStr}</span></td>
                <td data-label="Status"><span class="badge badge-success" style="background: var(--accent-emerald-subtle); color: var(--accent-emerald-dark);">Active (In Memory)</span></td>
                <td class="text-right" data-label="Actions">
                    <button class="btn btn-secondary btn-sm copy-key-btn" data-key="${keyStr}" title="Copy Key">
                        <i class="bi bi-clipboard"></i> Copy
                    </button>
                    <button class="btn btn-danger-outline btn-sm delete-key-btn" data-key="${keyStr}" title="Remove Key">
                        <i class="bi bi-trash3-fill"></i> Remove
                    </button>
                </td>
            `;
            dummyKeysTbody.appendChild(tr);
        });

        document.querySelectorAll(".copy-key-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const k = e.currentTarget.getAttribute("data-key");
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(k).then(() => {
                        showToast(`Copied key "${k}" to clipboard!`, "success");
                    }).catch(() => fallbackCopyTextToClipboard(k));
                } else {
                    fallbackCopyTextToClipboard(k);
                }
            });
        });

        function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.opacity = "0";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {
                const successful = document.execCommand('copy');
                if (successful) {
                    showToast(`Copied key "${text}" to clipboard!`, "success");
                } else {
                    showToast(`Failed to copy key.`, "error");
                }
            } catch (err) {
                showToast(`Failed to copy key.`, "error");
            }
            document.body.removeChild(textArea);
        }

        document.querySelectorAll(".delete-key-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const k = e.currentTarget.getAttribute("data-key");
                if (confirm(`Are you sure you want to revoke dummy API key "${k}"? Anyone using it will be disconnected.`)) {
                    await deleteDummyKey(k);
                }
            });
        });
    }

    async function createDummyKey() {
        if (!apiKey) {
            showToast("You must authenticate as Admin to create shared API keys.", "error");
            openAuthModal();
            return;
        }
        const customVal = inputCustomDummyKey ? inputCustomDummyKey.value.trim() : "";
        try {
            const res = await fetch("/admin/keys", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": apiKey
                },
                body: JSON.stringify({ key: customVal })
            });
            const data = await res.json();
            if (res.ok) {
                showToast(`Shared API key "${data.key}" created successfully!`, "success");
                if (inputCustomDummyKey) inputCustomDummyKey.value = "";
                renderDummyKeysTable(data.dummy_keys || []);
            } else if (res.status === 401) {
                handleAuthFailure("API key unauthorized.");
                openAuthModal();
            } else {
                showToast(data.error || "Failed to create dummy key.", "error");
            }
        } catch (error) {
            showToast("Network error while creating dummy key.", "error");
        }
    }

    async function deleteDummyKey(keyStr) {
        if (!apiKey) return;
        try {
            const res = await fetch(`/admin/keys?key=${encodeURIComponent(keyStr)}`, {
                method: "DELETE",
                headers: { "X-API-Key": apiKey }
            });
            const data = await res.json();
            if (res.ok) {
                showToast(`Removed dummy API key "${keyStr}".`, "info");
                renderDummyKeysTable(data.dummy_keys || []);
            } else {
                showToast(data.error || "Failed to delete key.", "error");
            }
        } catch (error) {
            showToast("Network error while removing key.", "error");
        }
    }

    // Start App
    init();
});
