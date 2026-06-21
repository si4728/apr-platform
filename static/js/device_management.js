let currentUser = null;
let users = [];
let fleets = [];
let devices = [];
let selectedFleetId = null;
let selectedDeviceRowId = null;

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

function userTopicLabel(userId) {
    const user = users.find(item => Number(item.id) === Number(userId));
    return user && user.user_topic_path ? user.user_topic_path : "";
}

function fleetTopicLabel(fleetId) {
    const fleet = fleets.find(item => Number(item.id) === Number(fleetId));
    return fleet && fleet.topic_path ? fleet.topic_path : "";
}

function normalizeTopicPart(text, fallback = "device") {
    const raw = String(text || fallback).trim() || fallback;
    return raw
        .replace(/\s+/g, "_")
        .replace(/[\\/]/g, "_")
        .replace(/[^\w.-]/g, "_")
        .replace(/_+/g, "_")
        .replace(/^[._-]+|[._-]+$/g, "") || fallback;
}

function cleanTopic(text) {
    return String(text || "").trim().replace(/^\/+|\/+$/g, "").replace(/\/+/g, "/");
}

function defaultTopicPrefix() {
    const fleetTopic = fleetTopicLabel(value("deviceFleet"));
    if (fleetTopic) {
        return fleetTopic;
    }
    return userTopicLabel(selectedOwnerUserId("deviceOwnerUser")) || "";
}

function generateDeviceTopics() {
    const deviceId = normalizeTopicPart(value("deviceId"), "device");
    const deviceType = normalizeTopicPart(value("deviceType"), "device");
    const prefix = cleanTopic(value("topicPrefix") || defaultTopicPrefix());
    if (!prefix) {
        setClientPackageStatus("Select owner/fleet or enter a topic prefix first.", true);
        return;
    }
    setValue("topicPrefix", prefix);
    setValue("telemetryTopic", `${prefix}/${deviceType}/${deviceId}`);
    setValue("policyTopic", `${prefix}/policy/${deviceId}`);
    setClientPackageStatus("Topics generated from the selected owner/fleet/device fields.");
}

function policyText(policy) {
    if (!policy) {
        return "-";
    }
    return `qos=${policy.qos}, ${policy.compression || "none"}, ${policy.encryption || "none"}, ${policy.integrity || "none"}`;
}

function setPolicyStatus(message, isError = false) {
    const node = el("policyStatus");
    if (!node) return;
    node.textContent = message;
    node.className = `policy-status-box ${isError ? "policy-error" : "policy-ok"}`;
}

function setTopicAuditStatus(message, isError = false) {
    const node = el("topicAuditStatus");
    if (!node) return;
    node.textContent = message;
    node.className = `policy-status-box ${isError ? "policy-error" : "policy-ok"}`;
}

function setClientPackageStatus(message, isError = false) {
    const node = el("clientPackageStatus");
    if (!node) return;
    node.textContent = message;
    node.className = `policy-status-box ${isError ? "policy-error" : "policy-ok"}`;
}

function setPolicyInputs(policy) {
    const safePolicy = policy || {};
    setValue("policyQos", safePolicy.qos === undefined ? "0" : safePolicy.qos);
    setValue("policyCompression", safePolicy.compression || "none");
    setValue("policyEncryption", safePolicy.encryption || "none");
    setValue("policyIntegrity", safePolicy.integrity || "none");
}

function buildPolicyPayload() {
    return {
        policy: {
            qos: Number(value("policyQos") || 0),
            compression: value("policyCompression") || "none",
            encryption: value("policyEncryption") || "none",
            integrity: value("policyIntegrity") || "none",
        },
        source: "manual",
    };
}

function selectedOwnerUserId(selectId) {
    if (currentUser && currentUser.role === "ADMIN") {
        return Number(value(selectId));
    }
    return currentUser ? Number(currentUser.id) : null;
}

function ownerOptionsHtml(selectedId) {
    return users.map(user => {
        const topic = user.user_topic_path ? ` / ${user.user_topic_path}` : "";
        const label = `${user.name} (${user.email}) - ${user.role}/${user.status}${topic}`;
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
            <td><code>${escapeHtml(fleet.topic_path || "-")}</code></td>
            <td>${escapeHtml(policyText(fleet.current_policy))}</td>
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
            <td>${escapeHtml(device.device_os || "raspberry_pi")}</td>
            <td>${escapeHtml(device.fleet_name || "-")}</td>
            <td>${escapeHtml(ownerLabel(device))}</td>
            <td><span class="status-badge ${device.status === "ACTIVE" ? "badge-active" : "badge-warning"}">${escapeHtml(device.status)}</span></td>
            <td>${escapeHtml(policyText(device.current_policy))}</td>
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
    selectedFleetId = fleet.id;
    setValue("fleetId", fleet.id);
    setValue("fleetName", fleet.name);
    setValue("fleetTopicName", fleet.topic_name || "");
    setValue("fleetDescription", fleet.description || "");
    setValue("fleetOwnerUser", fleet.owner_user_id);
    setValue("policyTargetLabel", `Fleet: ${fleet.name}`);
    setPolicyInputs(fleet.current_policy);
    setPolicyStatus(fleet.current_policy ? `Current fleet policy: ${policyText(fleet.current_policy)}` : "Fleet selected. No policy applied yet.");
}

function selectDevice(rowId) {
    const device = devices.find(item => Number(item.id) === Number(rowId));
    if (!device) return;
    selectedDeviceRowId = device.id;
    setValue("deviceRowId", device.id);
    setValue("deviceId", device.device_id);
    setValue("deviceName", device.device_name);
    setValue("deviceType", device.device_type || "raspberry_pi");
    setValue("deviceOs", device.device_os || "raspberry_pi");
    setValue("deviceStatus", device.status || "ACTIVE");
    setValue("deviceOwnerUser", device.owner_user_id);
    updateDeviceFleetOptions(device.fleet_id || "");
    setValue("deviceFleet", device.fleet_id || "");
    setValue("topicPrefix", device.topic_prefix || "iot/sensor");
    setValue("telemetryTopic", device.telemetry_topic || "");
    setValue("policyTopic", device.policy_topic || "");
    setValue("deviceDescription", device.description || "");
    setClientPackageStatus(`Client/test package is ready for ${device.device_id}. OS and topics can be changed and downloaded dynamically.`);
    setValue("policyTargetLabel", `Device: ${device.device_id}`);
    setPolicyInputs(device.current_policy);
    setPolicyStatus(device.current_policy ? `Current device policy: ${policyText(device.current_policy)}` : "Device selected. No policy applied yet.");
}

function clearFleetForm() {
    selectedFleetId = null;
    setValue("fleetId", "");
    setValue("fleetName", "");
    setValue("fleetTopicName", "");
    setValue("fleetDescription", "");
    setValue("fleetOwnerUser", currentUser ? currentUser.id : "");
}

function clearDeviceForm() {
    selectedDeviceRowId = null;
    setValue("deviceRowId", "");
    setValue("deviceId", "");
    setValue("deviceName", "");
    setValue("deviceType", "raspberry_pi");
    setValue("deviceOs", "raspberry_pi");
    setValue("deviceStatus", "ACTIVE");
    setValue("deviceOwnerUser", currentUser ? currentUser.id : "");
    setValue("topicPrefix", "");
    setValue("telemetryTopic", "");
    setValue("policyTopic", "");
    setValue("deviceDescription", "");
    setClientPackageStatus("Select OS and topics, then save or download the matching client/test package.");
    updateDeviceFleetOptions("");
}

function clearPolicyForm() {
    selectedFleetId = null;
    selectedDeviceRowId = null;
    setValue("policyTargetLabel", "");
    setPolicyInputs(null);
    setPolicyStatus("No policy target selected.");
}

function buildFleetPayload() {
    return {
        name: value("fleetName"),
        description: value("fleetDescription"),
        owner_user_id: selectedOwnerUserId("fleetOwnerUser"),
        topic_name: value("fleetTopicName"),
    };
}

function buildDevicePayload() {
    return {
        device_id: value("deviceId"),
        device_name: value("deviceName"),
        device_type: value("deviceType"),
        device_os: value("deviceOs"),
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

function downloadClientPackage() {
    const rowId = value("deviceRowId") || selectedDeviceRowId;
    if (!rowId) {
        setClientPackageStatus("Select or save a device before downloading the client/test package.", true);
        alert("Select or save a device first.");
        return;
    }
    const params = new URLSearchParams({
        device_os: value("deviceOs"),
        topic_prefix: value("topicPrefix"),
        telemetry_topic: value("telemetryTopic"),
        policy_topic: value("policyTopic"),
    });
    setClientPackageStatus("Downloading matching client/test package...");
    window.location.href = `/api/devices/${rowId}/client-package?${params.toString()}`;
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

async function applyPolicyToDevice() {
    const rowId = value("deviceRowId") || selectedDeviceRowId;
    if (!rowId) {
        alert("Select a device first.");
        return;
    }
    try {
        const data = await requestJson(`/api/devices/${rowId}/policy/apply`, {
            method: "POST",
            body: JSON.stringify(buildPolicyPayload()),
        });
        const result = data.result || {};
        setPolicyStatus(`Device policy applied: ${policyText(result.policy)} (${result.publish_status})${result.last_error ? ` - ${result.last_error}` : ""}`, result.publish_status !== "success");
        await loadData();
        selectedDeviceRowId = Number(rowId);
    } catch (err) {
        setPolicyStatus(`Device policy apply failed: ${err.message}`, true);
        alert(`Device policy apply failed: ${err.message}`);
    }
}

async function applyPolicyToFleet() {
    const fleetId = value("fleetId") || selectedFleetId;
    if (!fleetId) {
        alert("Select a fleet first.");
        return;
    }
    try {
        const data = await requestJson(`/api/fleets/${fleetId}/policy/apply`, {
            method: "POST",
            body: JSON.stringify(buildPolicyPayload()),
        });
        setPolicyStatus(`Fleet policy applied: ${policyText(data.policy)} (${data.publish_status}, devices=${(data.device_results || []).length})${data.last_error ? ` - ${data.last_error}` : ""}`, data.publish_status !== "success");
        await loadData();
        selectedFleetId = Number(fleetId);
    } catch (err) {
        setPolicyStatus(`Fleet policy apply failed: ${err.message}`, true);
        alert(`Fleet policy apply failed: ${err.message}`);
    }
}

function topicAuditMessage(data) {
    const summary = data.summary || {};
    const repaired = data.repaired || {};
    const parts = [
        `fleet issues=${summary.fleet_issue_count || 0}`,
        `device issues=${summary.device_issue_count || 0}`,
    ];
    if (data.repair_missing) {
        parts.push(`repaired fleets=${repaired.fleets || 0}`);
        parts.push(`repaired devices=${repaired.devices || 0}`);
    }
    const legacyCount = (data.devices || []).filter(device => (device.issues || []).includes("custom_or_legacy_topic_prefix")).length;
    if (legacyCount) {
        parts.push(`custom/legacy topics=${legacyCount}`);
    }
    return parts.join(", ");
}

async function auditTopics() {
    try {
        const data = await requestJson("/api/admin/topic-consistency");
        const issueCount = (data.summary?.fleet_issue_count || 0) + (data.summary?.device_issue_count || 0);
        setTopicAuditStatus(`Topic audit completed: ${topicAuditMessage(data)}`, issueCount > 0);
    } catch (err) {
        setTopicAuditStatus(`Topic audit failed: ${err.message}`, true);
        alert(`Topic audit failed: ${err.message}`);
    }
}

async function repairMissingTopics() {
    if (!confirm("Repair only missing default topic fields? Custom and legacy topics will be preserved.")) {
        return;
    }
    try {
        const data = await requestJson("/api/admin/topic-consistency/repair-missing", {method: "POST"});
        const issueCount = (data.summary?.fleet_issue_count || 0) + (data.summary?.device_issue_count || 0);
        setTopicAuditStatus(`Missing topic repair completed: ${topicAuditMessage(data)}`, issueCount > 0);
        await loadData();
    } catch (err) {
        setTopicAuditStatus(`Topic repair failed: ${err.message}`, true);
        alert(`Topic repair failed: ${err.message}`);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadCurrentUser();
    await loadData();
    el("deviceOwnerUser").addEventListener("change", () => {
        updateDeviceFleetOptions("");
        if (!value("topicPrefix")) {
            setValue("topicPrefix", defaultTopicPrefix());
        }
    });
    el("fleetOwnerUser").addEventListener("change", () => {
        setValue("deviceOwnerUser", value("fleetOwnerUser"));
        updateDeviceFleetOptions("");
        if (!value("topicPrefix")) {
            setValue("topicPrefix", defaultTopicPrefix());
        }
    });
    el("deviceFleet").addEventListener("change", () => {
        if (!value("topicPrefix")) {
            setValue("topicPrefix", defaultTopicPrefix());
        }
    });
});
