let currentUser = null;
let users = [];
let fleets = [];
let devices = [];

function el(id) {
    return document.getElementById(id);
}

function value(id) {
    const node = el(id);
    return node ? node.value.trim() : "";
}

function setValue(id, nextValue) {
    const node = el(id);
    if (node) {
        node.value = nextValue === undefined || nextValue === null ? "" : nextValue;
    }
}

function escapeHtml(text) {
    return String(text === undefined || text === null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function ownerLabel(row) {
    return row.owner_name ? `${row.owner_name} (${row.owner_email || "-"})` : "-";
}

function selectedOwnerUserId(selectId) {
    if (currentUser && currentUser.role === "ADMIN") {
        return Number(value(selectId));
    }
    return currentUser ? Number(currentUser.id) : null;
}

function ownerOptionsHtml(selectedId) {
    return users.map(user => {
        const label = `${user.name} (${user.email}) - ${user.role}/${user.status}`;
        const selected = Number(selectedId) === Number(user.id) ? "selected" : "";
        return `<option value="${user.id}" ${selected}>${escapeHtml(label)}</option>`;
    }).join("");
}

function fleetOptionsHtml(selectedId, ownerUserId) {
    const scoped = fleets.filter(fleet => Number(fleet.owner_user_id) === Number(ownerUserId));
    const empty = `<option value="">No fleet</option>`;
    return empty + scoped.map(fleet => {
        const selected = Number(selectedId) === Number(fleet.id) ? "selected" : "";
        return `<option value="${fleet.id}" ${selected}>${escapeHtml(fleet.name)}</option>`;
    }).join("");
}

async function requestJson(url, options = {}) {
    const res = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.error || `request failed: ${res.status}`);
    }
    return data;
}

async function loadCurrentUser() {
    const data = await requestJson("/api/auth/me");
    currentUser = data.user;
    if (currentUser.role === "ADMIN") {
        document.querySelectorAll(".admin-only").forEach(node => {
            node.style.display = "";
        });
        users = await requestJson("/api/admin/users/options");
    } else {
        users = [currentUser];
    }
    el("fleetOwnerUser").innerHTML = ownerOptionsHtml(currentUser.id);
    el("deviceOwnerUser").innerHTML = ownerOptionsHtml(currentUser.id);
}

async function loadData() {
    fleets = await requestJson("/api/fleets");
    devices = await requestJson("/api/devices");
    renderFleets();
    renderDevices();
    updateDeviceFleetOptions();
    updateSummary();
}

function renderFleets() {
    const table = el("fleetTable");
    table.innerHTML = fleets.map(fleet => `
        <tr onclick="selectFleet(${fleet.id})">
            <td>${escapeHtml(fleet.name)}</td>
            <td>${escapeHtml(ownerLabel(fleet))}</td>
            <td>${escapeHtml(fleet.description || "-")}</td>
            <td>${escapeHtml(fleet.created_at || "-")}</td>
        </tr>
    `).join("");
}

function renderDevices() {
    const table = el("deviceTable");
    table.innerHTML = devices.map(device => `
        <tr onclick="selectDevice(${device.id})">
            <td>${escapeHtml(device.device_id)}</td>
            <td>${escapeHtml(device.device_name)}</td>
            <td>${escapeHtml(device.device_type || "-")}</td>
            <td>${escapeHtml(device.fleet_name || "-")}</td>
            <td>${escapeHtml(ownerLabel(device))}</td>
            <td><span class="status-badge ${device.status === "ACTIVE" ? "badge-active" : "badge-warning"}">${escapeHtml(device.status)}</span></td>
            <td>${escapeHtml(device.telemetry_topic || "-")}</td>
            <td>${escapeHtml(device.policy_topic || "-")}</td>
        </tr>
    `).join("");
}

function updateSummary() {
    el("fleetCount").textContent = String(fleets.length);
    el("deviceCount").textContent = String(devices.length);
    el("activeDeviceCount").textContent = String(devices.filter(device => device.status === "ACTIVE").length);
}

function updateDeviceFleetOptions(selectedFleetId = value("deviceFleet")) {
    const ownerUserId = selectedOwnerUserId("deviceOwnerUser");
    el("deviceFleet").innerHTML = fleetOptionsHtml(selectedFleetId, ownerUserId);
}

function selectFleet(fleetId) {
    const fleet = fleets.find(item => Number(item.id) === Number(fleetId));
    if (!fleet) return;
    setValue("fleetId", fleet.id);
    setValue("fleetName", fleet.name);
    setValue("fleetDescription", fleet.description || "");
    setValue("fleetOwnerUser", fleet.owner_user_id);
}

function selectDevice(rowId) {
    const device = devices.find(item => Number(item.id) === Number(rowId));
    if (!device) return;
    setValue("deviceRowId", device.id);
    setValue("deviceId", device.device_id);
    setValue("deviceName", device.device_name);
    setValue("deviceType", device.device_type || "raspberry_pi");
    setValue("deviceStatus", device.status || "ACTIVE");
    setValue("deviceOwnerUser", device.owner_user_id);
    updateDeviceFleetOptions(device.fleet_id || "");
    setValue("deviceFleet", device.fleet_id || "");
    setValue("topicPrefix", device.topic_prefix || "iot/sensor");
    setValue("telemetryTopic", device.telemetry_topic || "");
    setValue("policyTopic", device.policy_topic || "");
    setValue("deviceDescription", device.description || "");
}

function clearFleetForm() {
    setValue("fleetId", "");
    setValue("fleetName", "");
    setValue("fleetDescription", "");
    setValue("fleetOwnerUser", currentUser ? currentUser.id : "");
}

function clearDeviceForm() {
    setValue("deviceRowId", "");
    setValue("deviceId", "");
    setValue("deviceName", "");
    setValue("deviceType", "raspberry_pi");
    setValue("deviceStatus", "ACTIVE");
    setValue("deviceOwnerUser", currentUser ? currentUser.id : "");
    setValue("topicPrefix", "iot/sensor");
    setValue("telemetryTopic", "");
    setValue("policyTopic", "");
    setValue("deviceDescription", "");
    updateDeviceFleetOptions("");
}

function buildFleetPayload() {
    return {
        name: value("fleetName"),
        description: value("fleetDescription"),
        owner_user_id: selectedOwnerUserId("fleetOwnerUser"),
    };
}

function buildDevicePayload() {
    return {
        device_id: value("deviceId"),
        device_name: value("deviceName"),
        device_type: value("deviceType"),
        status: value("deviceStatus"),
        owner_user_id: selectedOwnerUserId("deviceOwnerUser"),
        fleet_id: value("deviceFleet") || null,
        topic_prefix: value("topicPrefix"),
        telemetry_topic: value("telemetryTopic"),
        policy_topic: value("policyTopic"),
        description: value("deviceDescription"),
    };
}

async function saveFleet() {
    try {
        const fleetId = value("fleetId");
        const url = fleetId ? `/api/fleets/${fleetId}` : "/api/fleets";
        const method = fleetId ? "PUT" : "POST";
        await requestJson(url, {method, body: JSON.stringify(buildFleetPayload())});
        clearFleetForm();
        await loadData();
    } catch (err) {
        alert(`Fleet save failed: ${err.message}`);
    }
}

async function deleteFleet() {
    const fleetId = value("fleetId");
    if (!fleetId) {
        alert("Select a fleet first.");
        return;
    }
    if (!confirm("Delete selected fleet? Devices must be moved or deleted first.")) {
        return;
    }
    try {
        await requestJson(`/api/fleets/${fleetId}`, {method: "DELETE"});
        clearFleetForm();
        await loadData();
    } catch (err) {
        alert(`Fleet delete failed: ${err.message}`);
    }
}

async function saveDevice() {
    try {
        const rowId = value("deviceRowId");
        const url = rowId ? `/api/devices/${rowId}` : "/api/devices";
        const method = rowId ? "PUT" : "POST";
        await requestJson(url, {method, body: JSON.stringify(buildDevicePayload())});
        clearDeviceForm();
        await loadData();
    } catch (err) {
        alert(`Device save failed: ${err.message}`);
    }
}

async function deleteDevice() {
    const rowId = value("deviceRowId");
    if (!rowId) {
        alert("Select a device first.");
        return;
    }
    if (!confirm("Delete selected device?")) {
        return;
    }
    try {
        await requestJson(`/api/devices/${rowId}`, {method: "DELETE"});
        clearDeviceForm();
        await loadData();
    } catch (err) {
        alert(`Device delete failed: ${err.message}`);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadCurrentUser();
    await loadData();
    el("deviceOwnerUser").addEventListener("change", () => updateDeviceFleetOptions(""));
    el("fleetOwnerUser").addEventListener("change", () => {
        setValue("deviceOwnerUser", value("fleetOwnerUser"));
        updateDeviceFleetOptions("");
    });
});
