// sensor_config.js
// 센서 추가 / 수정 / 삭제 + 그래프 색상 구간 설정

let sensorTypes = [
    "temperature",
    "humidity",
    "vibration",
    "pressure",
    "co2"
];

let topicPrefix = "iot/sensor";


/* -----------------------------
   공통 유틸
----------------------------- */
function getElement(id) {
    return document.getElementById(id);
}


function getValue(id) {
    const obj = getElement(id);
    return obj ? obj.value.trim() : "";
}


function setValue(id, value) {
    const obj = getElement(id);

    if (!obj) return;

    obj.value =
        value === undefined || value === null
            ? ""
            : value;
}


function getNumberValue(id) {
    const value = getValue(id);

    if (value === "") {
        return null;
    }

    const numberValue = Number(value);

    if (Number.isNaN(numberValue)) {
        return null;
    }

    return numberValue;
}




function ensurePayloadSchemaModeControl() {
    if (getElement("payloadSchemaMode")) {
        return;
    }

    const topicInput = getElement("sensorTopic");

    if (!topicInput || !topicInput.parentElement) {
        return;
    }

    const select = document.createElement("select");
    select.id = "payloadSchemaMode";
    select.title = "payload schema mode";
    select.innerHTML = `
        <option value="defined_sensor">defined_sensor</option>
        <option value="strict_schema">strict_schema</option>
        <option value="flexible_json">flexible_json</option>
        <option value="raw_payload">raw_payload</option>
        <option value="binary_payload">binary_payload</option>
    `;

    topicInput.parentElement.appendChild(select);
}

function getPayloadSchemaMode() {
    const obj = getElement("payloadSchemaMode");
    return obj ? obj.value : "defined_sensor";
}

function setPayloadSchemaMode(value) {
    const obj = getElement("payloadSchemaMode");

    if (!obj) {
        return;
    }

    obj.value = value || "defined_sensor";
}

function ensurePayloadSchemaHeader() {
    const table = getElement("sensorConfigTable");

    if (!table) {
        return false;
    }

    const headerRow = table.closest("table")?.querySelector("thead tr");

    if (!headerRow) {
        return false;
    }

    const exists = Array.from(headerRow.children).some(th =>
        th.textContent.trim().toLowerCase().includes("payload") ||
        th.textContent.trim().toLowerCase().includes("schema")
    );

    if (!exists) {
        const th = document.createElement("th");
        th.textContent = "Payload Mode";

        const topicHeader = Array.from(headerRow.children).find(th =>
            th.textContent.trim().toLowerCase() === "topic"
        );

        if (topicHeader && topicHeader.nextSibling) {
            headerRow.insertBefore(th, topicHeader.nextSibling);
        } else {
            headerRow.appendChild(th);
        }
    }

    return true;
}

function emptyToDash(value) {
    if (value === undefined || value === null || value === "") {
        return "-";
    }

    return value;
}


/* -----------------------------
   Sensor Type Select
----------------------------- */
function loadSensorTypes() {
    const select = getElement("sensorType");

    if (!select) return;

    const currentValue = select.value;

    select.innerHTML = "";

    sensorTypes.forEach(type => {
        select.innerHTML += `
            <option value="${type}">
                ${type}
            </option>
        `;
    });

    if (currentValue && sensorTypes.includes(currentValue)) {
        select.value = currentValue;
    }
}


/* -----------------------------
   Topic 자동 생성
----------------------------- */
function updateTopicPreview() {
    const sensorId = getValue("sensorId");
    const sensorType = getValue("sensorType");

    if (!sensorId || !sensorType) {
        setValue("sensorTopic", "");
        return;
    }

    setValue(
        "sensorTopic",
        `${topicPrefix}/${sensorType}/${sensorId}`
    );
}


/* -----------------------------
   Type Modal
----------------------------- */
function openTypeModal() {
    getElement("typeModal").style.display = "block";
}


function closeTypeModal() {
    getElement("typeModal").style.display = "none";
}


function addNewType() {
    const typeName = getValue("newTypeName");

    if (!typeName) {
        alert("type name을 입력하세요.");
        return;
    }

    if (sensorTypes.includes(typeName)) {
        alert("이미 존재하는 type입니다.");
        return;
    }

    sensorTypes.push(typeName);

    loadSensorTypes();

    setValue("sensorType", typeName);
    setValue("newTypeName", "");

    updateTopicPreview();
    closeTypeModal();
}


/* -----------------------------
   Color Rule 생성
----------------------------- */
function buildColorRule() {
    const lowMax = getNumberValue("sensorLowMax");
    const normalMin = getNumberValue("sensorNormalMin");
    const normalMax = getNumberValue("sensorNormalMax");
    const highMin = getNumberValue("sensorHighMin");

    const hasAnyValue =
        lowMax !== null ||
        normalMin !== null ||
        normalMax !== null ||
        highMin !== null;

    if (!hasAnyValue) {
        return null;
    }

    if (
        lowMax === null ||
        normalMin === null ||
        normalMax === null ||
        highMin === null
    ) {
        alert(
            "색상 구간을 직접 설정하려면 낮음 최대값, 일반 최소값, 일반 최대값, 높음 최소값을 모두 입력하세요."
        );

        return false;
    }

    if (!(lowMax < normalMin && normalMin <= normalMax && normalMax < highMin)) {
        alert(
            "색상 구간은 다음 순서가 되도록 입력하세요.\\n낮음 최대값 < 일반 최소값 ≤ 일반 최대값 < 높음 최소값"
        );

        return false;
    }

    return {
        low_max: lowMax,
        normal_min: normalMin,
        normal_max: normalMax,
        high_min: highMin
    };
}


/* -----------------------------
   Sensor Object 생성
----------------------------- */
function buildSensorObject() {
    updateTopicPreview();

    const sensorId = getValue("sensorId");
    const sensorType = getValue("sensorType");

    if (!sensorId) {
        alert("sensor id를 입력하세요.");
        return null;
    }

    if (!sensorType) {
        alert("sensor type을 선택하세요.");
        return null;
    }

    const colorRule = buildColorRule();

    if (colorRule === false) {
        return null;
    }

    const sensor = {
        id: sensorId,
        type: sensorType,
        unit: getValue("sensorUnit"),
        topic: getValue("sensorTopic"),
        payload_schema_mode: getPayloadSchemaMode(),
        policy: getValue("sensorPolicy") || "none",
        min: getNumberValue("sensorMin"),
        max: getNumberValue("sensorMax"),
        start: getNumberValue("sensorStart"),
        step: getNumberValue("sensorStep"),
        interval: getNumberValue("sensorInterval"),
        mode: getValue("sensorMode")
    };

    if (colorRule !== null) {
        sensor.color_rule = colorRule;
    }

    return sensor;
}


/* -----------------------------
   Config Load
----------------------------- */
async function loadSensorConfig() {
    try {
        const res = await fetch("/api/config");

        if (!res.ok) {
            throw new Error("config load failed");
        }

        const config = await res.json();

        topicPrefix = config.mqtt.topic_prefix;

        ensurePayloadSchemaModeControl();
        ensurePayloadSchemaHeader();

        const table = getElement("sensorConfigTable");
        table.innerHTML = "";

        config.sensors.forEach(sensor => {
            if (!sensorTypes.includes(sensor.type)) {
                sensorTypes.push(sensor.type);
            }

            const rule = sensor.color_rule || null;

            const lowText = rule
                ? `≤ ${rule.low_max}`
                : "auto";

            const normalText = rule
                ? `${rule.normal_min} ~ ${rule.normal_max}`
                : "auto";

            const highText = rule
                ? `≥ ${rule.high_min}`
                : "auto";

            const safeSensorJson =
                JSON.stringify(sensor).replace(/'/g, "&#39;");

            table.innerHTML += `
                <tr onclick='selectSensor(${safeSensorJson})'>
                    <td>${emptyToDash(sensor.id)}</td>
                    <td>${emptyToDash(sensor.type)}</td>
                    <td>${emptyToDash(sensor.unit)}</td>
                    <td>${emptyToDash(sensor.topic)}</td>
                    <td>${emptyToDash(sensor.payload_schema_mode || "defined_sensor")}</td>
                    <td style="font-weight:bold; color:${sensor.policy === 'apr' ? '#0369a1' : '#6b7280'};">${emptyToDash(sensor.policy || "none")}</td>
                    <td>${emptyToDash(sensor.min)} ~ ${emptyToDash(sensor.max)}</td>
                    <td>${lowText}</td>
                    <td>${normalText}</td>
                    <td>${highText}</td>
                    <td>${emptyToDash(sensor.start)}</td>
                    <td>${emptyToDash(sensor.step)}</td>
                    <td>${emptyToDash(sensor.mode)}</td>
                    <td>${emptyToDash(sensor.interval)}</td>
                </tr>
            `;
        });

        loadSensorTypes();

    } catch (err) {
        console.error("loadSensorConfig error:", err);
        alert("센서 설정 정보를 불러오지 못했습니다.");
    }
}


/* -----------------------------
   Sensor 선택
----------------------------- */
function selectSensor(sensor) {
    setValue("sensorId", sensor.id);
    setValue("sensorType", sensor.type);
    setValue("sensorUnit", sensor.unit);
    setValue("sensorTopic", sensor.topic);
    setPayloadSchemaMode(sensor.payload_schema_mode || "defined_sensor");
    setValue("sensorPolicy", sensor.policy || "none");
    setValue("sensorMin", sensor.min);
    setValue("sensorMax", sensor.max);
    setValue("sensorStart", sensor.start);
    setValue("sensorStep", sensor.step);
    setValue("sensorInterval", sensor.interval);
    setValue("sensorMode", sensor.mode);

    const rule = sensor.color_rule || {};

    setValue("sensorLowMax", rule.low_max);
    setValue("sensorNormalMin", rule.normal_min);
    setValue("sensorNormalMax", rule.normal_max);
    setValue("sensorHighMin", rule.high_min);
}


/* -----------------------------
   Sensor 추가
----------------------------- */
async function addSensor() {
    const sensor = buildSensorObject();

    if (!sensor) return;

    try {
        const res = await fetch("/api/sensors", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(sensor)
        });

        if (!res.ok) {
            throw new Error("add failed");
        }

        await loadSensorConfig();
        clearForm();

    } catch (err) {
        console.error("addSensor error:", err);
        alert("센서 추가 실패");
    }
}


/* -----------------------------
   Sensor 수정
----------------------------- */
async function updateSensor() {
    const sensor = buildSensorObject();

    if (!sensor) return;

    try {
        const res = await fetch(`/api/sensors/${sensor.id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(sensor)
        });

        if (!res.ok) {
            throw new Error("update failed");
        }

        await loadSensorConfig();

    } catch (err) {
        console.error("updateSensor error:", err);
        alert("센서 수정 실패");
    }
}


/* -----------------------------
   Sensor 삭제
----------------------------- */
async function deleteSensor() {
    const sensorId = getValue("sensorId");

    if (!sensorId) {
        alert("삭제할 sensor id를 선택하세요.");
        return;
    }

    if (!confirm(`${sensorId} 센서를 삭제할까요?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/sensors/${sensorId}`, {
            method: "DELETE"
        });

        if (!res.ok) {
            throw new Error("delete failed");
        }

        await loadSensorConfig();
        clearForm();

    } catch (err) {
        console.error("deleteSensor error:", err);
        alert("센서 삭제 실패");
    }
}


/* -----------------------------
   Form 초기화
----------------------------- */
function clearForm() {
    [
        "sensorId",
        "sensorUnit",
        "sensorTopic",
        "sensorMin",
        "sensorMax",
        "sensorStart",
        "sensorStep",
        "sensorInterval",
        "sensorLowMax",
        "sensorNormalMin",
        "sensorNormalMax",
        "sensorHighMin"
    ].forEach(id => setValue(id, ""));

    if (sensorTypes.length > 0) {
        setValue("sensorType", sensorTypes[0]);
    }

    setValue("sensorMode", "random_walk");
    setPayloadSchemaMode("defined_sensor");
    setValue("sensorPolicy", "none");

    updateTopicPreview();
}


/* -----------------------------
   Event
----------------------------- */
document.addEventListener("DOMContentLoaded", async () => {
    ensurePayloadSchemaModeControl();
    ensurePayloadSchemaHeader();

    await loadSensorConfig();

    const sensorIdObj = getElement("sensorId");
    const sensorTypeObj = getElement("sensorType");

    if (sensorIdObj) {
        sensorIdObj.addEventListener("input", updateTopicPreview);
    }

    if (sensorTypeObj) {
        sensorTypeObj.addEventListener("change", updateTopicPreview);
    }

    updateTopicPreview();
});
