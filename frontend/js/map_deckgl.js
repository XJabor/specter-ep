const MAPBOX_TOKEN = window.SPECTER_CONFIG?.mapboxToken || '';

function setStatus(message) {
    const status = document.getElementById('status-bar');
    if (status) status.innerText = message;
}

window.setStatus = setStatus;

function setTerrainSourceStatus(message) {
    const status = document.getElementById('terrain-source-status');
    if (status) status.innerText = message;
}

function svgIcon(fillColor, shape) {
    const body = shape === 'satcom'
        ? `<path d="M32 10 L54 54 L10 54 Z" fill="${fillColor}" stroke="#ffffff" stroke-width="4"/>`
        : `<circle cx="32" cy="32" r="20" fill="${fillColor}" stroke="#ffffff" stroke-width="4"/><circle cx="32" cy="32" r="5" fill="#08100e"/>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">${body}</svg>`)}`;
}

const ICONS = {
    omni: { url: svgIcon('#00ffcc', 'omni'), width: 64, height: 64, anchorY: 32 },
    satcom: { url: svgIcon('#ff7e6b', 'satcom'), width: 64, height: 64, anchorY: 32 },
};

const deckgl = new deck.DeckGL({
    container: 'container',
    mapboxApiAccessToken: MAPBOX_TOKEN,
    mapStyle: 'mapbox://styles/mapbox/satellite-v9',
    initialViewState: {
        longitude: window.specterApp.state.previewEmitter.lon,
        latitude: window.specterApp.state.previewEmitter.lat,
        zoom: 10.5,
        pitch: 58,
        bearing: 0,
    },
    controller: true,
    layers: [],
    onClick: info => {
        if (info.object?.instanceId) {
            window.specterApp.selectInstance(info.object.instanceId);
            setStatus(`Selected ${info.object.label}.`);
            return;
        }

        if (!info.coordinate) return;
        const lon = info.coordinate[0];
        const lat = info.coordinate[1];

        if (window.specterApp.state.armedPlacement) {
            const instance = window.specterApp.placeArmedSystem(lat, lon);
            if (instance) {
                setStatus(`Placed ${instance.label}. Continue selecting systems from the right library.`);
            }
            return;
        }

        window.specterApp.updatePreviewEmitter(lat, lon);
        setStatus(`Preview point set: ${lat.toFixed(5)}, ${lon.toFixed(5)}. Arm a system from the right panel to place it.`);
    },
});

function offsetLatLon(lat, lon, distanceMeters, bearingRad) {
    const latOffset = (distanceMeters / 111000) * Math.cos(bearingRad);
    const lonOffset = (distanceMeters / (111000 * Math.cos(lat * Math.PI / 180))) * Math.sin(bearingRad);
    return { lat: lat + latOffset, lon: lon + lonOffset };
}

function buildVerticalBeamPolygon(instance) {
    const capMeters = instance.vertical_cap_m ?? 3048;
    const angleRad = Math.max(1, instance.elevation_deg) * (Math.PI / 180);
    const groundDistMeters = capMeters / Math.tan(angleRad);
    const halfSpreadMeters = Math.tan((instance.beamwidth_deg / 2) * Math.PI / 180) * groundDistMeters;
    const azRad = instance.azimuth_deg * Math.PI / 180;
    const leftAz = azRad - Math.PI / 2;
    const rightAz = azRad + Math.PI / 2;

    const center = offsetLatLon(instance.lat, instance.lon, groundDistMeters, azRad);
    const left = offsetLatLon(center.lat, center.lon, halfSpreadMeters, leftAz);
    const right = offsetLatLon(center.lat, center.lon, halfSpreadMeters, rightAz);

    return [
        [instance.lon, instance.lat, 0],
        [left.lon, left.lat, capMeters],
        [right.lon, right.lat, capMeters],
    ];
}

function instanceStateColor(instance, selected) {
    if (selected) return [255, 255, 255, 230];
    if (instance.calcState === 'error') return [255, 126, 107, 220];
    if (instance.type === 'satcom') return [255, 126, 107, 220];
    return [0, 255, 204, 220];
}

window.renderMapLayers = function renderMapLayers() {
    const state = window.specterApp.state;
    const selectedId = state.selectedInstanceId;

    const previewData = state.armedPlacement
        ? [{ lon: state.previewEmitter.lon, lat: state.previewEmitter.lat }]
        : [];

    const previewLayer = new deck.ScatterplotLayer({
        id: 'preview-emitter',
        data: previewData,
        pickable: false,
        radiusUnits: 'meters',
        getRadius: 85,
        getPosition: d => [d.lon, d.lat],
        getFillColor: [255, 255, 255, 28],
        getLineColor: [255, 255, 255, 180],
        lineWidthMinPixels: 2,
        stroked: true,
        filled: true,
    });

    const footprintData = state.placedSystems
        .filter(instance => instance.result?.polygon_points)
        .map(instance => ({
            instanceId: instance.instanceId,
            polygon: instance.result.polygon_points.map(([lat, lon]) => [lon, lat]),
        }));

    const footprintLayer = new deck.PolygonLayer({
        id: 'footprint-polygons',
        data: footprintData,
        pickable: false,
        stroked: true,
        filled: true,
        extruded: false,
        getPolygon: d => d.polygon,
        getFillColor: d => d.instanceId === selectedId ? [255, 255, 255, 70] : [255, 70, 40, 58],
        getLineColor: d => d.instanceId === selectedId ? [255, 255, 255, 230] : [255, 130, 80, 210],
        lineWidthMinPixels: 2,
    });

    const beamLayer = new deck.SolidPolygonLayer({
        id: 'satcom-beams',
        data: state.placedSystems
            .filter(instance => instance.result?.vertical_beam && instance.type === 'satcom')
            .map(instance => ({
                instanceId: instance.instanceId,
                polygon: buildVerticalBeamPolygon(instance),
            })),
        pickable: false,
        getPolygon: d => d.polygon,
        getFillColor: d => d.instanceId === selectedId ? [255, 255, 255, 80] : [0, 180, 255, 90],
        getLineColor: [180, 240, 255, 220],
        wireframe: true,
        extruded: false,
        lineWidthMinPixels: 2,
    });

    const iconLayer = new deck.IconLayer({
        id: 'system-icons',
        data: state.placedSystems,
        pickable: true,
        sizeScale: 1,
        getPosition: d => [d.lon, d.lat],
        getIcon: d => ICONS[d.type === 'satcom' ? 'satcom' : 'omni'],
        getSize: d => d.instanceId === selectedId ? 54 : 44,
    });

    const haloLayer = new deck.ScatterplotLayer({
        id: 'selection-halo',
        data: state.placedSystems.filter(instance => instance.instanceId === selectedId),
        pickable: false,
        radiusUnits: 'meters',
        getRadius: 110,
        getPosition: d => [d.lon, d.lat],
        getFillColor: [255, 255, 255, 24],
        getLineColor: [255, 255, 255, 220],
        lineWidthMinPixels: 2,
        stroked: true,
        filled: true,
    });

    const labelLayer = new deck.TextLayer({
        id: 'system-labels',
        data: state.placedSystems,
        pickable: false,
        getPosition: d => [d.lon, d.lat],
        getText: d => d.label,
        getSize: d => d.instanceId === selectedId ? 16 : 14,
        getColor: d => instanceStateColor(d, d.instanceId === selectedId),
        getPixelOffset: [0, 26],
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'bottom',
        fontFamily: 'monospace',
    });

    deckgl.setProps({
        layers: [
            footprintLayer,
            beamLayer,
            haloLayer,
            iconLayer,
            labelLayer,
            previewLayer,
        ],
    });
};

window.renderProgressPanel = function renderProgressPanel() {
    const progress = window.specterApp.state.progress;
    const total = Math.max(progress.total, 0);
    const count = progress.completed + progress.failed;
    const percent = total ? (count / total) * 100 : 0;
    document.getElementById('progress-bar').style.width = `${percent}%`;
    document.getElementById('progress-label').innerText = progress.running
        ? `${count}/${total} complete | active ${progress.activeLabel || 'starting'} | failures ${progress.failed}`
        : progress.message;
};

function updateTerrainSourceUi(terrain) {
    const input = document.getElementById('terrain_path');
    if (input && terrain.path) input.value = terrain.path;
    const warningText = terrain.warnings?.length ? ` | ${terrain.warnings.join(' ')}` : '';
    setTerrainSourceStatus(
        `Sources ${terrain.elevation_source_count}/${terrain.source_count} usable for elevation | imagery ${terrain.imagery_source_count}${warningText}`
    );
}

async function loadTerrainStatus() {
    try {
        const response = await fetch('/api/v1/terrain/status');
        const result = await response.json();
        if (result.status !== 'success') throw new Error(result.message || 'Terrain status failed');
        window.specterApp.state.terrainStatus = result.terrain;
        updateTerrainSourceUi(result.terrain);
    } catch (error) {
        setTerrainSourceStatus(`Terrain status error: ${error.message}`);
    }
}

window.refreshTerrainSource = async function refreshTerrainSource() {
    const path = document.getElementById('terrain_path')?.value?.trim();
    if (!path) {
        setTerrainSourceStatus('Enter a DTED folder, DTED file, or elevation GeoTIFF path.');
        return;
    }

    setTerrainSourceStatus('Scanning terrain source...');
    try {
        const response = await fetch('/api/v1/terrain/source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        });
        const result = await response.json();
        if (result.status !== 'success') throw new Error(result.message || 'Terrain scan failed');
        window.specterApp.state.terrainStatus = result.terrain;
        updateTerrainSourceUi(result.terrain);
        setStatus('Terrain source refreshed. Existing systems will use it on the next batch calculation.');
    } catch (error) {
        setTerrainSourceStatus(`Terrain scan error: ${error.message}`);
    }
};

function footprintRequestBody(instance) {
    return {
        tx_lat: instance.lat,
        tx_lon: instance.lon,
        freq_mhz: instance.freq_mhz,
        tx_power_dbm: instance.tx_power_dbm,
        antenna_gain_dbi: instance.antenna_gain_dbi,
        tx_height_m: instance.tx_height_m,
        rx_sensitivity_dbm: instance.rx_sensitivity_dbm,
        rx_gain_dbi: instance.rx_gain_dbi,
        cable_loss_db: instance.cable_loss_db,
        terrain: instance.terrain,
        antenna_type: instance.type,
        azimuth_deg: instance.azimuth_deg,
        elevation_deg: instance.elevation_deg,
        beamwidth_deg: instance.beamwidth_deg,
        num_bearings: 72,
        num_samples: 25,
        vertical_cap_m: instance.vertical_cap_m,
    };
}

async function calculateFootprintForInstance(instance) {
    const response = await fetch('/api/v1/footprint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(footprintRequestBody(instance)),
    });
    const result = await response.json();
    if (result.status !== 'success') {
        throw new Error(result.message || 'Footprint calculation failed');
    }
    return result;
}

window.calculateAllFootprints = async function calculateAllFootprints() {
    const systems = window.specterApp.state.placedSystems;
    if (!systems.length) {
        setStatus('Place at least one system before starting batch footprint calculation.');
        return;
    }
    if (window.specterApp.state.progress.running) return;

    window.specterApp.beginBatchProgress(systems.length);
    setStatus(`Calculating ${systems.length} system footprints sequentially.`);

    let completed = 0;
    let failed = 0;

    for (const instance of systems) {
        instance.calcState = 'running';
        window.specterApp.updateBatchProgress({
            completed,
            failed,
            activeLabel: instance.label,
            message: `Calculating ${instance.label}...`,
        });

        try {
            instance.result = await calculateFootprintForInstance(instance);
            instance.calcState = 'done';
            instance.error = null;
            completed += 1;
        } catch (error) {
            instance.result = null;
            instance.calcState = 'error';
            instance.error = error.message;
            failed += 1;
        }

        window.specterApp.refreshUi();
    }

    const message = failed
        ? `Batch complete. ${completed} succeeded, ${failed} failed.`
        : `Batch complete. ${completed} system footprints calculated.`;
    window.specterApp.finishBatchProgress(message);
    setStatus(message);
};

window.runModel = window.calculateAllFootprints;

window.specterApp.refreshUi();
window.renderMapLayers();
window.renderProgressPanel();
loadTerrainStatus();
