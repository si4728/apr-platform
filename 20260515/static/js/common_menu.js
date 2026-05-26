function loadCommonMenu() {

    const menuHtml = `

        <div class="sidebar-title">
            IoT Simulation
        </div>

        <div class="sidebar-menu">

            <button onclick="location.href='/'">
                단일 센서 대시보드
            </button>

            <button onclick="location.href='/all_dashboard'">
                전체 센서 보기
            </button>

            <button onclick="location.href='/sensor_config'">
                센서 설정 관리
            </button>

        </div>
    `;

    const target =
        document.getElementById(
            "commonMenu"
        );

    if (target) {
        target.innerHTML = menuHtml;
    }
}

document.addEventListener(
    "DOMContentLoaded",
    loadCommonMenu
);

/* --------------------------------
   Sidebar Toggle
-------------------------------- */

function toggleSidebar() {

    const sidebar =
        document.querySelector(".sidebar");

    if (!sidebar) return;

    sidebar.classList.toggle("collapsed");
}


document.addEventListener(
    "DOMContentLoaded",
    () => {

        const btn =
            document.createElement("button");

        btn.className =
            "sidebar-toggle-btn";

        btn.innerHTML = "☰";

        btn.onclick = toggleSidebar;

        document.body.appendChild(btn);
    }
);