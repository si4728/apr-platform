function loadCommonMenu() {
    const path = window.location.pathname;

    const menuHtml = `
        <div class="sidebar-title">
            IoT Simulation
        </div>

        <div class="sidebar-menu" style="padding-bottom: 10px;">
            <select id="menuSelect" style="width: 100%; padding: 10px; font-size: 14px; border-radius: 4px; border: 1px solid #ccc; background-color: #f8fafc; cursor: pointer;" onchange="if(this.value) location.href=this.value">
                <option value="/" ${path === '/' ? 'selected' : ''}>Telemetry Dashboard</option>
                <option value="/all_dashboard" ${path === '/all_dashboard' ? 'selected' : ''}>All Sensors</option>
                <option value="/sensor_config" ${path === '/sensor_config' ? 'selected' : ''}>Sensor Config</option>
                <option value="/queue_dashboard" ${path === '/queue_dashboard' ? 'selected' : ''}>Queue Monitor</option>
                <option value="/latency_dashboard" ${path === '/latency_dashboard' ? 'selected' : ''}>Latency Analysis</option>
                <option value="/experiment_dashboard" ${path === '/experiment_dashboard' ? 'selected' : ''}>Experiment Runner</option>
                <option value="/schema_dashboard" ${path === '/schema_dashboard' ? 'selected' : ''}>Schema Intelligence</option>
                <option value="/apr_dashboard" ${path === '/apr_dashboard' ? 'selected' : ''}>APR Dashboard</option>
                <option value="/voice_dashboard" ${path === '/voice_dashboard' ? 'selected' : ''}>Voice Streaming</option>
                <option value="/device_edge_doc" ${path === '/device_edge_doc' ? 'selected' : ''}>Device Edge README</option>
                <option value="/server_operation_manual" ${path === '/server_operation_manual' ? 'selected' : ''}>Server Operation Manual</option>
            </select>
        </div>
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
