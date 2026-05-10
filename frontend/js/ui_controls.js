function getPlacementStatusText() {
    const { armedPlacement } = window.specterApp.state;
    if (!armedPlacement) return 'No system armed for placement.';
    const system = window.specterApp.findSystem(armedPlacement.category, armedPlacement.presetId);
    return system ? `Placement armed: click the map to place ${system.name}.` : 'Placement armed.';
}

function renderSystemCard(system, category, isSelected) {
    const typeLabel = system.type === 'satcom' ? 'SATCOM' : 'GROUND';
    return `
        <div class="system-card ${isSelected ? 'is-selected' : ''}" onclick="armSystemPlacement('${category}', '${system.id}')">
            <div class="card-title">
                <span>${system.name}</span>
                <span class="state-pill">${typeLabel}</span>
            </div>
            <div class="card-meta">
                ${system.default_freq_mhz} MHz | ${system.max_power_dbm} dBm | gain ${system.antenna_gain_dbi ?? 0} dBi
            </div>
        </div>
    `;
}

function renderPlacedSystemCard(instance, isSelected) {
    return `
        <div class="placed-system-card ${isSelected ? 'is-selected' : ''}" onclick="selectPlacedSystem('${instance.instanceId}')">
            <div class="card-title">
                <span>${instance.label}</span>
                <span class="state-pill state-${instance.calcState}">${instance.calcState}</span>
            </div>
            <div class="card-meta">
                ${instance.name} | ${instance.lat.toFixed(4)}, ${instance.lon.toFixed(4)}
            </div>
        </div>
    `;
}

function numericField(label, field, value, step, min = '', max = '', fullWidth = false) {
    return `
        <div class="${fullWidth ? 'full-width' : ''}">
            <label>${label}</label>
            <input type="number" value="${value}" step="${step}" min="${min}" max="${max}"
                onchange="updateSelectedSystemField('${field}', this.value)">
        </div>
    `;
}

function textField(label, field, value, fullWidth = false) {
    const escaped = String(value ?? '').replace(/"/g, '&quot;');
    return `
        <div class="${fullWidth ? 'full-width' : ''}">
            <label>${label}</label>
            <input type="text" value="${escaped}" onchange="updateSelectedSystemField('${field}', this.value)">
        </div>
    `;
}

window.renderLibraryPanel = function renderLibraryPanel() {
    const list = document.getElementById('systems-library-list');
    const placementStatus = document.getElementById('placement-mode-status');
    const customBuilder = document.getElementById('custom-system-builder');
    const { armedPlacement } = window.specterApp.state;
    const draft = window.specterApp.state.customDraft;

    placementStatus.innerText = getPlacementStatusText();

    list.innerHTML = window.specterApp.getLibrarySections().map(section => `
        <div class="section">
            <h3>${section.title}</h3>
            <div class="system-list">
                ${section.items.length
                    ? section.items.map(system => renderSystemCard(
                        system,
                        section.key,
                        armedPlacement?.category === section.key && armedPlacement?.presetId === system.id
                    )).join('')
                    : '<div class="empty-state">No systems in this section.</div>'}
            </div>
        </div>
    `).join('');

    customBuilder.innerHTML = `
        <div class="full-width">
            <label>Name</label>
            <input type="text" id="custom_name" value="${String(draft.name).replace(/"/g, '&quot;')}" placeholder="Custom emitter name"
                onchange="updateCustomDraftField('name', this.value)">
        </div>
        <div>
            <label>Type</label>
            <select id="custom_type" onchange="updateCustomDraftField('type', this.value)">
                <option value="omni" ${draft.type === 'omni' ? 'selected' : ''}>Ground Omni</option>
                <option value="satcom" ${draft.type === 'satcom' ? 'selected' : ''}>SATCOM</option>
            </select>
        </div>
        <div>
            <label>Frequency (MHz)</label>
            <input type="number" id="custom_freq_mhz" value="${draft.default_freq_mhz}" step="1"
                onchange="updateCustomDraftField('default_freq_mhz', this.value)">
        </div>
        <div>
            <label>Tx Power (dBm)</label>
            <input type="number" id="custom_tx_power_dbm" value="${draft.max_power_dbm}" step="0.5"
                onchange="updateCustomDraftField('max_power_dbm', this.value)">
        </div>
        <div>
            <label>Gain (dBi)</label>
            <input type="number" id="custom_gain" value="${draft.antenna_gain_dbi}" step="0.5"
                onchange="updateCustomDraftField('antenna_gain_dbi', this.value)">
        </div>
        <div>
            <label>Height AGL (m)</label>
            <input type="number" id="custom_height" value="${draft.default_height_m}" step="0.5"
                onchange="updateCustomDraftField('default_height_m', this.value)">
        </div>
        <div class="full-width">
            <label>Collector Sensitivity (dBm)</label>
            <input type="number" id="custom_sensitivity" value="${draft.rx_sensitivity_dbm}" step="1"
                onchange="updateCustomDraftField('rx_sensitivity_dbm', this.value)">
        </div>
        <div class="full-width">
            <label>Beamwidth (deg)</label>
            <input type="number" id="custom_beamwidth" value="${draft.beamwidth_deg}" step="1" min="1" max="360"
                onchange="updateCustomDraftField('beamwidth_deg', this.value)">
        </div>
        <div class="full-width">
            <label>Notes</label>
            <textarea id="custom_notes" placeholder="Session-only notes for this custom system."
                onchange="updateCustomDraftField('notes', this.value)">${draft.notes ?? ''}</textarea>
        </div>
    `;
};

window.renderInstancePanel = function renderInstancePanel() {
    const placedList = document.getElementById('placed-systems-list');
    const empty = document.getElementById('instance-editor-empty');
    const editor = document.getElementById('instance-editor');
    const removeButton = document.getElementById('remove-selected-btn');
    const selected = window.specterApp.getSelectedInstance();

    placedList.innerHTML = window.specterApp.state.placedSystems.length
        ? window.specterApp.state.placedSystems.map(instance => renderPlacedSystemCard(
            instance,
            instance.instanceId === window.specterApp.state.selectedInstanceId
        )).join('')
        : '<div class="empty-state">No systems placed yet.</div>';

    if (!selected) {
        empty.classList.remove('hidden');
        editor.classList.add('hidden');
        removeButton.classList.add('hidden');
        editor.innerHTML = '';
        return;
    }

    empty.classList.add('hidden');
    editor.classList.remove('hidden');
    removeButton.classList.remove('hidden');

    const resultSummary = selected.result?.summary
        ? `<div class="microcopy full-width">Last run: ${selected.result.summary.min_range_km.toFixed(2)}-${selected.result.summary.max_range_km.toFixed(2)} km | LOS ${selected.result.summary.los_sector_count}/${selected.result.sectors.length}</div>`
        : `<div class="microcopy full-width">No footprint calculated for this instance yet.</div>`;

    editor.innerHTML = `
        <div class="field-grid">
            ${textField('Label', 'label', selected.label, true)}
            ${numericField('Latitude', 'lat', selected.lat, 0.00001)}
            ${numericField('Longitude', 'lon', selected.lon, 0.00001)}
            ${numericField('Frequency (MHz)', 'freq_mhz', selected.freq_mhz, 1)}
            ${numericField('Tx Power (dBm)', 'tx_power_dbm', selected.tx_power_dbm, 0.5)}
            ${numericField('Gain (dBi)', 'antenna_gain_dbi', selected.antenna_gain_dbi, 0.5)}
            ${numericField('Height AGL (m)', 'tx_height_m', selected.tx_height_m, 0.5)}
            ${numericField('Collector Sensitivity (dBm)', 'rx_sensitivity_dbm', selected.rx_sensitivity_dbm, 1)}
            ${numericField('Azimuth (deg)', 'azimuth_deg', selected.azimuth_deg, 1, 0, 360)}
            ${numericField('Elevation Angle (deg)', 'elevation_deg', selected.elevation_deg, 1, 0, 90)}
            ${numericField('Beamwidth (deg)', 'beamwidth_deg', selected.beamwidth_deg, 1, 1, 360)}
            <div>
                <label>Terrain / Clutter</label>
                <select onchange="updateSelectedSystemField('terrain', this.value)">
                    <option value="rural" ${selected.terrain === 'rural' ? 'selected' : ''}>Rural / Open</option>
                    <option value="light forest" ${selected.terrain === 'light forest' ? 'selected' : ''}>Light Forest / Suburban</option>
                    <option value="dense forest" ${selected.terrain === 'dense forest' ? 'selected' : ''}>Dense Forest / Urban</option>
                    <option value="free space" ${selected.terrain === 'free space' ? 'selected' : ''}>Free Space / Aerial</option>
                </select>
            </div>
            <div>
                <label>Type</label>
                <select onchange="updateSelectedSystemField('type', this.value)">
                    <option value="omni" ${selected.type === 'omni' ? 'selected' : ''}>Ground Omni</option>
                    <option value="satcom" ${selected.type === 'satcom' ? 'selected' : ''}>SATCOM</option>
                </select>
            </div>
            ${resultSummary}
        </div>
    `;
};

window.renderProgressPanel = function renderProgressPanel() {
    const progress = window.specterApp.state.progress;
    const bar = document.getElementById('progress-bar');
    const label = document.getElementById('progress-label');
    const total = Math.max(progress.total, 0);
    const percent = total ? ((progress.completed + progress.failed) / total) * 100 : 0;
    bar.style.width = `${percent}%`;
    label.innerText = progress.running
        ? `${progress.completed + progress.failed}/${total} complete | active ${progress.activeLabel || 'initializing'} | failures ${progress.failed}`
        : progress.message;
};

window.armSystemPlacement = function armSystemPlacement(category, presetId) {
    window.specterApp.armPlacement(category, presetId);
};

window.selectPlacedSystem = function selectPlacedSystem(instanceId) {
    window.specterApp.selectInstance(instanceId);
};

window.updateSelectedSystemField = function updateSelectedSystemField(field, rawValue) {
    const numericFields = new Set([
        'lat', 'lon', 'freq_mhz', 'tx_power_dbm', 'antenna_gain_dbi', 'tx_height_m',
        'rx_sensitivity_dbm', 'azimuth_deg', 'elevation_deg', 'beamwidth_deg'
    ]);
    const value = numericFields.has(field) ? Number(rawValue) : rawValue;
    window.specterApp.updateSelectedInstanceField(field, value);
};

window.createCustomSystem = function createCustomSystem() {
    const draft = window.specterApp.state.customDraft;
    const systemName = draft.name.trim();
    if (!systemName) {
        if (typeof window.setStatus === 'function') window.setStatus('Custom systems need a name before they can be added.');
        return;
    }

    const input = {
        name: systemName,
        type: draft.type,
        default_freq_mhz: Number(draft.default_freq_mhz || 300),
        max_power_dbm: Number(draft.max_power_dbm || 37),
        antenna_gain_dbi: Number(draft.antenna_gain_dbi || 2),
        default_height_m: Number(draft.default_height_m || 2),
        rx_sensitivity_dbm: Number(draft.rx_sensitivity_dbm || -100),
        beamwidth_deg: Number(draft.beamwidth_deg || 15),
        notes: draft.notes.trim(),
    };
    window.specterApp.createCustomSystem(input);
    if (typeof window.setStatus === 'function') window.setStatus(`Custom system added. Click the map to place ${input.name}.`);
};

window.updateCustomDraftField = function updateCustomDraftField(field, rawValue) {
    const numericFields = new Set([
        'default_freq_mhz', 'max_power_dbm', 'antenna_gain_dbi', 'default_height_m',
        'rx_sensitivity_dbm', 'beamwidth_deg'
    ]);
    window.specterApp.state.customDraft[field] = numericFields.has(field) ? Number(rawValue) : rawValue;
};

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const response = await fetch('/api/v1/systems');
        const systemsLibrary = await response.json();
        window.specterApp.setSystemsLibrary(systemsLibrary);
    } catch (error) {
        console.error('Could not load systems library:', error);
    }
});
