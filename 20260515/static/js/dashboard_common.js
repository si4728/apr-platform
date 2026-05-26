// dashboard_common.js
// Single / Multi dashboard 공통 그래프 처리
// 색상 규칙:
// - 센서별 color_rule 정의 있음: low / normal / high 구간 적용
// - color_rule 정의 없음: 데이터 평균 기준 ±15% 자동 적용
// - 높음: 빨강, 일반: 녹색, 낮음: 노랑

let charts = {};
let singleChart = null;
let currentSingleSensorId = null;
let refreshTimer = null;

const sensorAxisRange = {
    "temp_001": {
        min: 15,
        max: 45
    },
    "humi_001": {
        min: 20,
        max: 100
    },
    "vib_001": {
        min: 0,
        max: 12
    }
};


/* --------------------------------
   공통 유틸
-------------------------------- */
function safeId(id) {
    return String(id).replace(
        /[^a-zA-Z0-9_]/g,
        "_"
    );
}


function getAverage(values) {
    if (!values || values.length === 0) {
        return 0;
    }

    const numericValues =
        values.map(v => Number(v))
              .filter(v => !Number.isNaN(v));

    if (numericValues.length === 0) {
        return 0;
    }

    const sum =
        numericValues.reduce(
            (acc, value) => acc + value,
            0
        );

    return sum / numericValues.length;
}


function getYAxisRange(sensorId, values) {
    if (sensorAxisRange[sensorId]) {
        return sensorAxisRange[sensorId];
    }

    if (!values || values.length === 0) {
        return {
            min: 0,
            max: 100
        };
    }

    const numericValues =
        values.map(v => Number(v))
              .filter(v => !Number.isNaN(v));

    if (numericValues.length === 0) {
        return {
            min: 0,
            max: 100
        };
    }

    const minValue =
        Math.min(...numericValues);

    const maxValue =
        Math.max(...numericValues);

    if (minValue === maxValue) {
        return {
            min: minValue - 5,
            max: maxValue + 5
        };
    }

    return {
        min: Math.floor(minValue - 5),
        max: Math.ceil(maxValue + 5)
    };
}


/* --------------------------------
   Color Rule 확인
-------------------------------- */
function hasDefinedColorRule(sensor) {
    if (!sensor || !sensor.color_rule) {
        return false;
    }

    const rule = sensor.color_rule;

    return (
        rule.low_max !== undefined &&
        rule.low_max !== null &&
        rule.normal_min !== undefined &&
        rule.normal_min !== null &&
        rule.normal_max !== undefined &&
        rule.normal_max !== null &&
        rule.high_min !== undefined &&
        rule.high_min !== null
    );
}


/* --------------------------------
   값 상태 계산
-------------------------------- */
function getValueStatus(sensor, value, values) {
    const numericValue = Number(value);

    if (Number.isNaN(numericValue)) {
        return {
            status: "NORMAL",
            color: "green",
            className: "chart-status-normal"
        };
    }

    /*
       1) 센서별 color_rule이 정의된 경우
    */
    if (hasDefinedColorRule(sensor)) {
        const rule = sensor.color_rule;

        const lowMax = Number(rule.low_max);
        const normalMin = Number(rule.normal_min);
        const normalMax = Number(rule.normal_max);
        const highMin = Number(rule.high_min);

        if (numericValue >= highMin) {
            return {
                status: "HIGH",
                color: "red",
                className: "chart-status-critical"
            };
        }

        if (numericValue <= lowMax) {
            return {
                status: "LOW",
                color: "#facc15",
                className: "chart-status-warning"
            };
        }

        if (
            numericValue >= normalMin &&
            numericValue <= normalMax
        ) {
            return {
                status: "NORMAL",
                color: "green",
                className: "chart-status-normal"
            };
        }

        /*
           구간 사이에 빈 영역이 있을 경우 보정
           normal_min보다 낮으면 LOW, normal_max보다 높으면 HIGH
        */
        if (numericValue < normalMin) {
            return {
                status: "LOW",
                color: "#facc15",
                className: "chart-status-warning"
            };
        }

        return {
            status: "HIGH",
            color: "red",
            className: "chart-status-critical"
        };
    }

    /*
       2) 센서별 정의가 없는 경우
       평균 ±15%를 일반 구간으로 적용
    */
    const average = getAverage(values);

    if (average === 0) {
        return {
            status: "NORMAL",
            color: "green",
            className: "chart-status-normal"
        };
    }

    const lowLimit = average * 0.85;
    const highLimit = average * 1.15;

    if (numericValue < lowLimit) {
        return {
            status: "LOW",
            color: "#facc15",
            className: "chart-status-warning"
        };
    }

    if (numericValue > highLimit) {
        return {
            status: "HIGH",
            color: "red",
            className: "chart-status-critical"
        };
    }

    return {
        status: "NORMAL",
        color: "green",
        className: "chart-status-normal"
    };
}


/* --------------------------------
   Config 정보 표시
-------------------------------- */
async function loadConfigInfo() {
    try {
        const res = await fetch("/api/config");
        const config = await res.json();

        if (document.getElementById("brokerInfo")) {
            document.getElementById("brokerInfo").innerText =
                `${config.mqtt.broker}:${config.mqtt.port}`;
        }

        if (document.getElementById("topicPrefix")) {
            document.getElementById("topicPrefix").innerText =
                config.mqtt.topic_prefix;
        }

        if (document.getElementById("sensorCount")) {
            document.getElementById("sensorCount").innerText =
                config.sensors.length;
        }

        if (document.getElementById("sensorList")) {
            const sensorList =
                document.getElementById("sensorList");

            sensorList.innerHTML = "";

            config.sensors.forEach(sensor => {
                let ruleText = "AUTO: AVG ±15%";

                if (hasDefinedColorRule(sensor)) {
                    const rule = sensor.color_rule;

                    ruleText =
                        `LOW≤${rule.low_max}, ` +
                        `NORMAL ${rule.normal_min}~${rule.normal_max}, ` +
                        `HIGH≥${rule.high_min}`;
                }

                sensorList.innerHTML += `
                    <div class="info-item">
                        ${sensor.id}
                        <br>
                        <span class="info-label">
                            ${sensor.type} / ${sensor.unit}
                        </span>
                        <br>
                        <span class="info-label">
                            ${ruleText}
                        </span>
                    </div>
                `;
            });
        }

    } catch (err) {
        console.error("loadConfigInfo error:", err);
    }
}


/* --------------------------------
   Sensor Select
-------------------------------- */
async function loadSensorSelect() {
    if (!document.getElementById("sensorSelect")) {
        return;
    }

    const res = await fetch("/api/sensors");
    const sensors = await res.json();

    const select =
        document.getElementById("sensorSelect");

    const currentValue = select.value;

    select.innerHTML = "";

    sensors.forEach(sensor => {
        select.innerHTML += `
            <option value="${sensor.id}">
                ${sensor.id} / ${sensor.type}
            </option>
        `;
    });

    if (currentValue) {
        select.value = currentValue;
    }
}


/* --------------------------------
   Single Dashboard
-------------------------------- */
async function loadSingleDashboard() {
    const select =
        document.getElementById("sensorSelect");

    if (!select) return;

    const sensorId = select.value;

    if (!sensorId) return;

    const sensorsRes = await fetch("/api/sensors");
    const sensors = await sensorsRes.json();

    const sensor =
        sensors.find(s => s.id === sensorId) || {
            id: sensorId
        };

    const dataLimit =
        parseInt(
            document.getElementById("dataLimit").value
        );

    const tickInterval =
        parseInt(
            document.getElementById("tickInterval").value
        );

    const res =
        await fetch(
            `/api/chart/${sensorId}?limit=${dataLimit}&_=${Date.now()}`
        );

    const data = await res.json();

    updateSingleChart(
        sensor,
        data.labels,
        data.values,
        tickInterval
    );
}


/* --------------------------------
   Single Chart
   - Single Dashboard는 하나의 canvas(sensorChart)를 공유함
   - 센서가 바뀌면 기존 Chart를 destroy한 뒤 새로 생성
-------------------------------- */
function updateSingleChart(sensor, labels, values, tickInterval) {
    const sensorId = sensor.id;

    const canvas =
        document.getElementById("sensorChart");

    if (!canvas) return;

    const yRange =
        getYAxisRange(sensorId, values);

    const sensorChanged =
        currentSingleSensorId !== null &&
        currentSingleSensorId !== sensorId;

    if (sensorChanged && singleChart) {
        singleChart.destroy();
        singleChart = null;
    }

    currentSingleSensorId = sensorId;

    if (!singleChart) {
        singleChart =
            new Chart(canvas, {
                type: "line",

                data: {
                    labels: labels,

                    datasets: [{
                        label: sensorId,
                        data: values,
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius: 2,

                        segment: {
                            borderColor: context => {
                                const y = context.p1.parsed.y;

                                return getValueStatus(
                                    sensor,
                                    y,
                                    values
                                ).color;
                            }
                        },

                        pointBackgroundColor: context => {
                            const y = context.parsed.y;

                            return getValueStatus(
                                sensor,
                                y,
                                values
                            ).color;
                        }
                    }]
                },

                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,

                    plugins: {
                        legend: {
                            display: true
                        },

                        tooltip: {
                            callbacks: {
                                afterLabel: context => {
                                    const y = context.parsed.y;

                                    const info =
                                        getValueStatus(
                                            sensor,
                                            y,
                                            values
                                        );

                                    return `Status: ${info.status}`;
                                }
                            }
                        }
                    },

                    scales: {
                        x: {
                            ticks: {
                                callback: function(value, index) {
                                    if (index % tickInterval === 0) {
                                        return this.getLabelForValue(value);
                                    }

                                    return "";
                                }
                            }
                        },

                        y: {
                            min: yRange.min,
                            max: yRange.max
                        }
                    }
                }
            });

    } else {
        singleChart.data.labels = labels;
        singleChart.data.datasets[0].label = sensorId;
        singleChart.data.datasets[0].data = values;

        singleChart.data.datasets[0].segment.borderColor = context => {
            const y = context.p1.parsed.y;

            return getValueStatus(
                sensor,
                y,
                values
            ).color;
        };

        singleChart.data.datasets[0].pointBackgroundColor = context => {
            const y = context.parsed.y;

            return getValueStatus(
                sensor,
                y,
                values
            ).color;
        };

        singleChart.options.scales.y.min = yRange.min;
        singleChart.options.scales.y.max = yRange.max;

        singleChart.update("none");
    }
}


/* --------------------------------
   Multi Dashboard
-------------------------------- */
async function loadMultiDashboard() {
    const res = await fetch("/api/sensors");
    const sensors = await res.json();

    const dataLimit =
        parseInt(
            document.getElementById("dataLimit").value
        );

    const tickInterval =
        parseInt(
            document.getElementById("tickInterval").value
        );

    const container =
        document.getElementById("multiCharts");

    if (!container) return;

    const currentIds =
        sensors.map(s => s.id);

    Object.keys(charts).forEach(sensorId => {
        if (!currentIds.includes(sensorId)) {
            charts[sensorId].destroy();
            delete charts[sensorId];

            const panel =
                document.getElementById(
                    `panel_${safeId(sensorId)}`
                );

            if (panel) {
                panel.remove();
            }
        }
    });

    sensors.forEach(sensor => {
        const panelId =
            `panel_${safeId(sensor.id)}`;

        const canvasId =
            `chart_${safeId(sensor.id)}`;

        const statusId =
            `status_${safeId(sensor.id)}`;

        if (!document.getElementById(panelId)) {
            container.innerHTML += `
                <div class="chart-panel" id="${panelId}">
                    <div class="chart-title">
                        ${sensor.id} / ${sensor.type} / ${sensor.unit}
                    </div>

                    <div class="chart-canvas-box">
                        <canvas id="${canvasId}"></canvas>
                    </div>

                    <div class="chart-status-box">
                        STATUS :
                        <span id="${statusId}">
                            NORMAL
                        </span>
                    </div>
                </div>
            `;
        }
    });

    for (const sensor of sensors) {
        const chartRes =
            await fetch(
                `/api/chart/${sensor.id}?limit=${dataLimit}`
            );

        const data =
            await chartRes.json();

        updateMultiChart(
            sensor,
            data.labels,
            data.values,
            tickInterval
        );
    }
}


/* --------------------------------
   Multi Chart
-------------------------------- */
function updateMultiChart(sensor, labels, values, tickInterval) {
    const sensorId = sensor.id;

    const canvas =
        document.getElementById(
            `chart_${safeId(sensorId)}`
        );

    if (!canvas) return;

    const yRange =
        getYAxisRange(sensorId, values);

    const latestValue =
        values && values.length > 0
            ? values[values.length - 1]
            : null;

    if (latestValue !== null) {
        const latestStatus =
            getValueStatus(
                sensor,
                latestValue,
                values
            );

        const statusObj =
            document.getElementById(
                `status_${safeId(sensorId)}`
            );

        if (statusObj) {
            statusObj.innerText =
                `${latestStatus.status} (${latestValue})`;

            statusObj.className =
                latestStatus.className;
        }
    }

    if (!charts[sensorId]) {
        charts[sensorId] =
            new Chart(canvas, {
                type: "line",

                data: {
                    labels: labels,

                    datasets: [{
                        label: `${sensor.id} (${sensor.unit})`,
                        data: values,
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius: 2,

                        segment: {
                            borderColor: context => {
                                const y = context.p1.parsed.y;

                                return getValueStatus(
                                    sensor,
                                    y,
                                    values
                                ).color;
                            }
                        },

                        pointBackgroundColor: context => {
                            const y = context.parsed.y;

                            return getValueStatus(
                                sensor,
                                y,
                                values
                            ).color;
                        }
                    }]
                },

                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,

                    interaction: {
                        intersect: false,
                        mode: "index"
                    },

                    plugins: {
                        legend: {
                            display: true
                        },

                        tooltip: {
                            callbacks: {
                                afterLabel: context => {
                                    const y = context.parsed.y;

                                    const info =
                                        getValueStatus(
                                            sensor,
                                            y,
                                            values
                                        );

                                    return `Status: ${info.status}`;
                                }
                            }
                        }
                    },

                    scales: {
                        x: {
                            ticks: {
                                callback: function(value, index) {
                                    if (index % tickInterval === 0) {
                                        return this.getLabelForValue(value);
                                    }

                                    return "";
                                }
                            }
                        },

                        y: {
                            min: yRange.min,
                            max: yRange.max
                        }
                    }
                }
            });

    } else {
        const chart = charts[sensorId];

        chart.data.labels = labels;
        chart.data.datasets[0].data = values;

        chart.data.datasets[0].segment.borderColor = context => {
            const y = context.p1.parsed.y;

            return getValueStatus(
                sensor,
                y,
                values
            ).color;
        };

        chart.data.datasets[0].pointBackgroundColor = context => {
            const y = context.parsed.y;

            return getValueStatus(
                sensor,
                y,
                values
            ).color;
        };

        chart.options.scales.y.min = yRange.min;
        chart.options.scales.y.max = yRange.max;

        chart.update("none");
    }
}


/* --------------------------------
   Refresh
-------------------------------- */
async function refreshDashboard() {
    await loadConfigInfo();

    if (pageMode === "single") {
        await loadSingleDashboard();
    } else {
        await loadMultiDashboard();
    }
}


/* --------------------------------
   Refresh Timer
-------------------------------- */
function startRefreshTimer() {
    const refreshObj =
        document.getElementById("refreshInterval");

    if (!refreshObj) return;

    if (refreshTimer) {
        clearInterval(refreshTimer);
    }

    const interval =
        parseInt(refreshObj.value);

    refreshTimer =
        setInterval(
            refreshDashboard,
            interval
        );
}


/* --------------------------------
   Init
-------------------------------- */
async function initializeDashboard() {
    await loadSensorSelect();
    await refreshDashboard();

    startRefreshTimer();

    const sensorSelect =
        document.getElementById("sensorSelect");

    const dataLimit =
        document.getElementById("dataLimit");

    const tickInterval =
        document.getElementById("tickInterval");

    const refreshInterval =
        document.getElementById("refreshInterval");

    if (sensorSelect) {
        sensorSelect.addEventListener(
            "change",
            async () => {
                await loadSingleDashboard();
            }
        );
    }

    if (dataLimit) {
        dataLimit.addEventListener(
            "change",
            refreshDashboard
        );
    }

    if (tickInterval) {
        tickInterval.addEventListener(
            "change",
            refreshDashboard
        );
    }

    if (refreshInterval) {
        refreshInterval.addEventListener(
            "change",
            startRefreshTimer
        );
    }
}


document.addEventListener(
    "DOMContentLoaded",
    initializeDashboard
);
