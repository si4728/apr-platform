async function getCurrentUser() {
    try {
        const res = await fetch("/api/auth/me", {cache: "no-store"});
        if (!res.ok) {
            return null;
        }
        const data = await res.json();
        return data.user || null;
    } catch (err) {
        console.warn("failed to load current user", err);
        return null;
    }
}

function menuOption(item, path) {
    return `<option value="${item.href}" ${path === item.href ? "selected" : ""}>${item.label}</option>`;
}

async function loadCommonMenu() {
    const path = window.location.pathname;
    const user = await getCurrentUser();
    const isAdmin = user && user.role === "ADMIN";

    const userItems = [
        {href: "/", label: "Telemetry Dashboard"},
        {href: "/all_dashboard", label: "All Sensors"},
        {href: "/latency_dashboard", label: "Latency Analysis"},
        {href: "/device_management", label: "Device/Fleet Management"},
        {href: "/device_edge_doc", label: "Device Edge README"},
    ];

    const adminItems = [
        {href: "/sensor_config", label: "Sensor Config"},
        {href: "/queue_dashboard", label: "Queue Monitor"},
        {href: "/experiment_dashboard", label: "Experiment Runner"},
        {href: "/schema_dashboard", label: "Schema Intelligence"},
        {href: "/apr_dashboard", label: "APR Dashboard"},
        {href: "/voice_dashboard", label: "Voice Streaming"},
        {href: "/server_operation_manual", label: "Server Operation Manual"},
        {href: "/admin/users", label: "User Management"},
        {href: "/admin/access-logs", label: "Access Logs"},
        {href: "/admin/audit-logs", label: "Audit Logs"},
    ];

    const items = isAdmin ? userItems.concat(adminItems) : userItems;
    const menuHtml = `
        <div class="sidebar-title">
            IoT Simulation
        </div>

        <div class="current-user-box">
            <div class="current-user-name">${user ? user.name : "Guest"}</div>
            <div class="current-user-meta">${user ? `${user.role} / ${user.status}` : ""}</div>
        </div>

        <div class="sidebar-menu" style="padding-bottom: 10px;">
            <select id="menuSelect" style="width: 100%; padding: 10px; font-size: 14px; border-radius: 4px; border: 1px solid #ccc; background-color: #f8fafc; cursor: pointer;" onchange="if(this.value) location.href=this.value">
                ${items.map(item => menuOption(item, path)).join("")}
            </select>
        </div>

        <a class="logout-link" href="/logout">Logout</a>
    `;

    const target = document.getElementById("commonMenu");
    if (target) {
        target.innerHTML = menuHtml;
    }
}

document.addEventListener("DOMContentLoaded", loadCommonMenu);

function toggleSidebar() {
    document.body.classList.toggle("sidebar-collapsed");
}

document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("sidebarToggle");
    if (btn) {
        btn.addEventListener("click", toggleSidebar);
    }
});
