const DEFAULT_EMITTER = { lat: 21.4765, lon: -157.9647 };

function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
}

function createInstanceFromSystem(system, category, instanceId, lat, lon) {
    return {
        instanceId,
        presetId: system.id,
        category,
        name: system.name,
        label: system.name,
        type: system.type || "omni",
        lat,
        lon,
        freq_mhz: system.default_freq_mhz ?? 300,
        tx_power_dbm: system.max_power_dbm ?? 37,
        antenna_gain_dbi: system.antenna_gain_dbi ?? 0,
        tx_height_m: system.default_height_m ?? 2,
        rx_sensitivity_dbm: system.rx_sensitivity_dbm ?? -100,
        rx_gain_dbi: system.rx_gain_dbi ?? 0,
        cable_loss_db: system.cable_loss_db ?? 0,
        terrain: system.terrain ?? "rural",
        azimuth_deg: system.azimuth_deg ?? 180,
        elevation_deg: system.elevation_deg ?? 45,
        beamwidth_deg: system.beamwidth_deg ?? (system.type === "satcom" ? 15 : 360),
        vertical_cap_m: system.vertical_cap_m ?? 3048,
        notes: system.notes ?? "",
        calcState: "idle",
        result: null,
        error: null,
    };
}

const specterApp = {
    state: {
        systemsLibrary: {
            tactical_radios: [],
            satcom_terminals: [],
            custom_systems: [],
        },
        armedPlacement: null,
        previewEmitter: { ...DEFAULT_EMITTER },
        placedSystems: [],
        selectedInstanceId: null,
        instanceCounter: 0,
        customCounter: 0,
        terrainStatus: null,
        progress: {
            running: false,
            total: 0,
            completed: 0,
            failed: 0,
            activeLabel: "",
            message: "No calculation in progress.",
        },
        customDraft: {
            name: "",
            type: "omni",
            default_freq_mhz: 300,
            max_power_dbm: 37,
            antenna_gain_dbi: 2,
            default_height_m: 2,
            rx_sensitivity_dbm: -100,
            beamwidth_deg: 15,
            notes: "",
        },
    },

    refreshUi() {
        if (typeof window.renderLibraryPanel === "function") window.renderLibraryPanel();
        if (typeof window.renderInstancePanel === "function") window.renderInstancePanel();
        if (typeof window.renderMapLayers === "function") window.renderMapLayers();
        if (typeof window.renderProgressPanel === "function") window.renderProgressPanel();
    },

    setSystemsLibrary(data) {
        this.state.systemsLibrary = {
            tactical_radios: data.tactical_radios || [],
            satcom_terminals: data.satcom_terminals || [],
            custom_systems: data.custom_systems || [],
        };
        this.refreshUi();
    },

    getLibrarySections() {
        return [
            { key: "tactical_radios", title: "Ground Radios", items: this.state.systemsLibrary.tactical_radios },
            { key: "satcom_terminals", title: "SATCOM Terminals", items: this.state.systemsLibrary.satcom_terminals },
            { key: "custom_systems", title: "Session Custom Systems", items: this.state.systemsLibrary.custom_systems },
        ];
    },

    findSystem(category, presetId) {
        return (this.state.systemsLibrary[category] || []).find(system => system.id === presetId) || null;
    },

    armPlacement(category, presetId) {
        this.state.armedPlacement = { category, presetId };
        this.refreshUi();
    },

    clearPlacementMode() {
        this.state.armedPlacement = null;
        this.refreshUi();
    },

    updatePreviewEmitter(lat, lon) {
        this.state.previewEmitter = { lat, lon };
        if (typeof window.renderMapLayers === "function") window.renderMapLayers();
    },

    placeArmedSystem(lat, lon) {
        if (!this.state.armedPlacement) return null;
        const { category, presetId } = this.state.armedPlacement;
        const system = this.findSystem(category, presetId);
        if (!system) return null;
        const instanceId = `instance_${++this.state.instanceCounter}`;
        const instance = createInstanceFromSystem(system, category, instanceId, lat, lon);
        this.state.placedSystems.push(instance);
        this.state.selectedInstanceId = instanceId;
        this.state.armedPlacement = null;
        this.refreshUi();
        return instance;
    },

    selectInstance(instanceId) {
        this.state.selectedInstanceId = instanceId;
        this.refreshUi();
    },

    getSelectedInstance() {
        return this.state.placedSystems.find(instance => instance.instanceId === this.state.selectedInstanceId) || null;
    },

    updateSelectedInstanceField(field, value) {
        const instance = this.getSelectedInstance();
        if (!instance) return;
        instance[field] = value;
        instance.calcState = instance.calcState === "running" ? "running" : "idle";
        if (field !== "label") {
            instance.result = null;
            instance.error = null;
        }
        this.refreshUi();
    },

    removeSelectedInstance() {
        const selectedId = this.state.selectedInstanceId;
        if (!selectedId) return;
        this.state.placedSystems = this.state.placedSystems.filter(instance => instance.instanceId !== selectedId);
        this.state.selectedInstanceId = this.state.placedSystems[0]?.instanceId || null;
        this.refreshUi();
    },

    clearPlacedSystems() {
        this.state.placedSystems = [];
        this.state.selectedInstanceId = null;
        this.state.progress = {
            running: false,
            total: 0,
            completed: 0,
            failed: 0,
            activeLabel: "",
            message: "No calculation in progress.",
        };
        this.refreshUi();
    },

    createCustomSystem(input) {
        const customId = `custom_${++this.state.customCounter}`;
        const customSystem = {
            id: customId,
            name: input.name,
            type: input.type,
            default_freq_mhz: input.default_freq_mhz,
            max_power_dbm: input.max_power_dbm,
            antenna_gain_dbi: input.antenna_gain_dbi,
            default_height_m: input.default_height_m,
            rx_sensitivity_dbm: input.rx_sensitivity_dbm,
            beamwidth_deg: input.beamwidth_deg,
            notes: input.notes,
        };
        this.state.systemsLibrary.custom_systems.push(customSystem);
        this.armPlacement("custom_systems", customId);
        this.state.customDraft = {
            name: "",
            type: "omni",
            default_freq_mhz: 300,
            max_power_dbm: 37,
            antenna_gain_dbi: 2,
            default_height_m: 2,
            rx_sensitivity_dbm: -100,
            beamwidth_deg: 15,
            notes: "",
        };
        this.refreshUi();
        return customSystem;
    },

    beginBatchProgress(total) {
        this.state.progress = {
            running: true,
            total,
            completed: 0,
            failed: 0,
            activeLabel: "",
            message: total ? "Preparing batch calculation..." : "No systems placed.",
        };
        this.state.placedSystems.forEach(instance => {
            instance.calcState = "queued";
            instance.error = null;
        });
        this.refreshUi();
    },

    updateBatchProgress({ completed, failed, activeLabel, message }) {
        this.state.progress = {
            ...this.state.progress,
            completed,
            failed,
            activeLabel,
            message,
        };
        this.refreshUi();
    },

    finishBatchProgress(message) {
        this.state.progress = {
            ...this.state.progress,
            running: false,
            activeLabel: "",
            message,
        };
        this.refreshUi();
    },
};

window.specterApp = specterApp;
window.clearFootprints = () => {
    specterApp.clearPlacedSystems();
    if (typeof window.setStatus === "function") {
        window.setStatus("Cleared placed systems and footprint results.");
    }
};

window.removeSelectedSystem = () => {
    const removed = specterApp.getSelectedInstance()?.label || "selected system";
    specterApp.removeSelectedInstance();
    if (typeof window.setStatus === "function") {
        window.setStatus(`Removed ${removed}.`);
    }
};
