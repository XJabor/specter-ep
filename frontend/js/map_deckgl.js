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

function markerFillColor(instance, selectedId) {
    if (instance.instanceId === selectedId) return [255, 255, 255, 230];
    if (instance.type === 'satcom') return [255, 126, 107, 220];
    return [0, 255, 204, 220];
}

function dragStatusText(instance, lat, lon, action = 'Moving') {
    return `${action} ${instance.label}: ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}
const containerElement = document.getElementById('container');
const markerOverlayElement = document.getElementById('system-marker-overlay');
const dragState = {
    activeInstanceId: null,
    pointerId: null,
};
let currentViewState = {
    longitude: window.specterApp.state.previewEmitter.lon,
    latitude: window.specterApp.state.previewEmitter.lat,
    zoom: 10.5,
    pitch: 58,
    bearing: 0,
};

const deckgl = new deck.DeckGL({
    container: 'container',
    mapboxApiAccessToken: MAPBOX_TOKEN,
    mapStyle: 'mapbox://styles/mapbox/satellite-v9',
    initialViewState: currentViewState,
    controller: true,
    layers: [],
    onClick: info => {
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
    onViewStateChange: ({viewState}) => {
        currentViewState = { ...viewState };
        if (typeof window.renderMapMarkersOverlay === 'function') window.renderMapMarkersOverlay();
        return viewState;
    },
});

containerElement.addEventListener('contextmenu', e => e.preventDefault());

function getViewport() {
    return new deck.WebMercatorViewport({
        ...currentViewState,
        width: Math.max(containerElement.clientWidth, 1),
        height: Math.max(containerElement.clientHeight, 1),
    });
}

function moveMarkerFromPointer(clientX, clientY, statusAction) {
    if (!dragState.activeInstanceId) return;
    const rect = containerElement.getBoundingClientRect();
    const viewport = getViewport();
    const [lon, lat] = viewport.unproject([clientX - rect.left, clientY - rect.top]);
    const instance = window.specterApp.moveInstance(dragState.activeInstanceId, lat, lon);
    if (instance) setStatus(dragStatusText(instance, lat, lon, statusAction));
}

function endMarkerDrag() {
    if (!dragState.activeInstanceId) return;
    const movedInstance = window.specterApp.findInstance(dragState.activeInstanceId);
    if (movedInstance) {
        setStatus(dragStatusText(movedInstance, movedInstance.lat, movedInstance.lon, 'Moved'));
    }
    dragState.activeInstanceId = null;
    dragState.pointerId = null;
    if (typeof window.renderMapMarkersOverlay === 'function') window.renderMapMarkersOverlay();
}

document.addEventListener('pointermove', event => {
    if (dragState.pointerId !== event.pointerId || !dragState.activeInstanceId) return;
    event.preventDefault();
    moveMarkerFromPointer(event.clientX, event.clientY, 'Moving');
});

document.addEventListener('pointerup', event => {
    if (dragState.pointerId !== event.pointerId) return;
    event.preventDefault();
    endMarkerDrag();
});

document.addEventListener('pointercancel', event => {
    if (dragState.pointerId !== event.pointerId) return;
    endMarkerDrag();
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
            labelLayer,
            previewLayer,
        ],
    });
};

window.renderMapMarkersOverlay = function renderMapMarkersOverlay() {
    if (!markerOverlayElement) return;
    markerOverlayElement.innerHTML = '';
    const viewport = getViewport();
    const { placedSystems, selectedInstanceId } = window.specterApp.state;

    placedSystems.forEach(instance => {
        const [x, y] = viewport.project([instance.lon, instance.lat]);
        const marker = document.createElement('button');
        marker.type = 'button';
        marker.className = [
            'system-map-marker',
            instance.type === 'satcom' ? 'satcom' : 'ground',
            instance.instanceId === selectedInstanceId ? 'selected' : '',
            instance.instanceId === dragState.activeInstanceId ? 'dragging' : '',
        ].filter(Boolean).join(' ');
        marker.style.left = `${x}px`;
        marker.style.top = `${y}px`;
        marker.title = instance.label;
        marker.setAttribute('aria-label', `Move ${instance.label}`);

        marker.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            if (dragState.activeInstanceId) return;
            window.specterApp.selectInstance(instance.instanceId);
            setStatus(`Selected ${instance.label}.`);
        });

        marker.addEventListener('pointerdown', event => {
            event.preventDefault();
            event.stopPropagation();
            dragState.activeInstanceId = instance.instanceId;
            dragState.pointerId = event.pointerId;
            window.specterApp.selectInstance(instance.instanceId);
            marker.setPointerCapture(event.pointerId);
            moveMarkerFromPointer(event.clientX, event.clientY, 'Repositioning');
            window.renderMapMarkersOverlay();
        });

        markerOverlayElement.appendChild(marker);
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
