// dashboard/script.js
let globalAnomaliesData = [];
let safeZonesData = [];
let globalTrajectories = [];
let anomalyMarkers = []; 
let globalHubs = [];
let rawTemporalData = [];
let appConfig = { hubNames: {}, ignoredRoutes: {}, ignoredHubs: [], safeZones: [] };

// Helper to translate route names based on user hub names
function translateRoute(rawRoute) {
    if (!rawRoute || rawRoute === "Unknown Route") return rawRoute;
    let newRoute = rawRoute;
    let savedHubs = appConfig.hubNames || {};
    globalHubs.forEach(h => {
        let name = savedHubs[h.id] || h.id;
        newRoute = newRoute.replace(new RegExp(h.id, 'g'), name);
    });
    return newRoute;
}

document.addEventListener("DOMContentLoaded", () => {
    Promise.all([
        fetch('/api/config').then(r => r.json()).catch(() => ({ hubNames: {}, ignoredRoutes: {}, ignoredHubs: [], safeZones: [] })),
        fetch('data.json.gz')
            .then(r => {
                const ds = new DecompressionStream('gzip');
                const decompressedStream = r.body.pipeThrough(ds);
                return new Response(decompressedStream).json();
            })
            .catch(() => fetch('data.json').then(r => r.json()))
    ]).then(([configData, data]) => {
            appConfig = configData;
            let ignoredRoutes = appConfig.ignoredRoutes || {};
            let ignoredHubs = appConfig.ignoredHubs || [];
            
            // Merge safe zones from DB with any from data.json
            let combinedSafeZones = [...(data.safeZones || [])];
            let dbSafeZones = appConfig.safeZones || [];
            let existingSzIds = new Set(combinedSafeZones.map(s => s.id));
            dbSafeZones.forEach(sz => { if(!existingSzIds.has(sz.id)) combinedSafeZones.push(sz); });
            data.safeZones = combinedSafeZones;
            
            let isRouteIgnored = (route) => {
                if(!route) return true;
                if(ignoredRoutes[route]) return true;
                for(let h of ignoredHubs) {
                    if(route.includes(h)) return true;
                }
                return false;
            };
            
            globalAnomaliesData = (data.anomalies || []).filter(a => !isRouteIgnored(a.route));
            safeZonesData = data.safeZones || [];
            globalTrajectories = (data.trajectories || []).filter(t => !isRouteIgnored(t.route));
            globalHubs = (data.hubs || []).filter(h => !ignoredHubs.includes(h.id));
            rawTemporalData = (data.temporalTraffic || []).filter(t => !isRouteIgnored(t.route));
            let etaPreds = (data.etaPredictions || []).filter(p => !isRouteIgnored(p.route));
            
            initKPIs(data.kpis);
            initHubConfig();
            initGlobalMap(data.hotspots);
            initAnomaliesMap();
            initETAModels(etaPreds);
            renderAnomaliesTable();
            Dashboard.initGeofenceMap();
            Dashboard.renderSafeZonesList();
            initTemporalAnalysis();
            setupNavigation();
        });

    const collapseBtn = document.getElementById('poi-collapse-btn');
    if (collapseBtn) {
        collapseBtn.addEventListener('click', () => {
            document.getElementById('poi-analysis-container').style.display = 'none';
            document.getElementById('view-hotspots').scrollIntoView({behavior: 'smooth'});
        });
    }
});

function createMapWithLayers(containerId, center, zoom) {
    let darkLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap', subdomains: 'abcd', maxZoom: 20
    });
    let satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri', maxZoom: 18
    });
    let map = L.map(containerId, { center: center, zoom: zoom, layers: [darkLayer] });
    L.control.layers({"Dark Map": darkLayer, "Satellite": satelliteLayer}).addTo(map);
    return map;
}

function setupNavigation() {
    const links = document.querySelectorAll('.nav-menu a');
    links.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            links.forEach(l => l.classList.remove('active'));
            e.currentTarget.classList.add('active');
            
            const view = e.currentTarget.getAttribute('data-view');
            sessionStorage.setItem('activeTab', view);
            document.querySelectorAll('.view-section').forEach(sec => sec.style.display = 'none');
            
            if (view === 'all') {
                document.querySelectorAll('.view-section:not(.split-section):not(#view-hubs):not(#view-eta)').forEach(sec => sec.style.display = 'flex');
                document.getElementById('view-anomalies').style.display = 'none';
            } else {
                let target = document.getElementById('view-' + view);
                if(target) target.style.display = 'flex';
                if(view === 'anomalies') setTimeout(() => anomaliesMap.invalidateSize(), 100);
                if(view === 'geofence') setTimeout(() => Dashboard.geofenceMap.invalidateSize(), 100);
                if(view === 'hubs') setTimeout(() => hubsMap.invalidateSize(), 100);
                if(view === 'eta') setTimeout(() => etaMap.invalidateSize(), 100);
            }
        });
    });
    let savedTab = sessionStorage.getItem('activeTab');
    if(savedTab) {
        let active = document.querySelector('.nav-menu a[data-view="'+savedTab+'"]');
        if(active) { active.click(); return; }
    }
    let active = document.querySelector('.nav-menu a.active');
    if(active) active.click();
}

// HUB CONFIGURATION
let hubsMap;
function initHubConfig() {
    const list = document.getElementById('hubs-list');
    if (!list) return;
    
    hubsMap = createMapWithLayers('hubs-map', [22.7196, 75.8577], 5);
    
    let savedHubs = appConfig.hubNames || {};
    let markers = [];
    
    globalHubs.forEach(h => {
        let currentName = savedHubs[h.id] || h.id;
        
        let marker = L.marker([h.lat, h.lon]).addTo(hubsMap);
        marker.bindPopup(`
            <div style="text-align: left; min-width: 160px; padding: 4px;">
                <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">Hub ID: ${h.id}</p>
                <input type="text" id="popup-input-${h.id.replace(' ','')}" value="${currentName}" class="modal-input" style="padding: 6px 10px; margin-bottom: 12px; width: 100%; border-radius: 6px; box-sizing: border-box;">
                <div style="display: flex; gap: 8px;">
                    <button class="btn-primary" style="padding: 6px 12px; font-size: 12px; flex: 1; border-radius: 6px; justify-content: center;" onclick="saveHubNameFromPopup('${h.id}')">Save</button>
                    <button class="btn-secondary" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: none; padding: 6px 12px; font-size: 12px; flex: 1; border-radius: 6px; justify-content: center;" onclick="deleteHub('${h.id}')">Delete</button>
                </div>
            </div>
        `);
        markers.push(marker);
        
        let html = `
            <div style="display: flex; gap: 12px; align-items: center; background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
                <input type="checkbox" class="hub-delete-cb" data-id="${h.id}" style="width: 16px; height: 16px; cursor: pointer;">
                <div style="flex: 1;">
                    <label style="font-size: 12px; color: var(--text-muted);">${h.id} (${h.lat}, ${h.lon})</label>
                    <input type="text" id="hub-input-${h.id.replace(' ','')}" class="input-modern" value="${currentName}" style="width: 100%; margin-top: 4px;">
                </div>
            </div>
        `;
        list.insertAdjacentHTML('beforeend', html);
    });
    
    if(markers.length > 0) {
        let group = new L.featureGroup(markers);
        hubsMap.fitBounds(group.getBounds().pad(0.2));
    }
    
    let savedRoutes = appConfig.ignoredRoutes || {};
    let routesSet = new Set();
    globalTrajectories.forEach(t => routesSet.add(t.route));
    // Also add any previously ignored routes so they can be turned back on
    Object.keys(savedRoutes).forEach(r => routesSet.add(r));
    
    const rList = document.getElementById('routes-list');
    routesSet.forEach(r => {
        let isChecked = savedRoutes[r] ? '' : 'checked';
        rList.insertAdjacentHTML('beforeend', `
            <div style="display: flex; align-items: center; gap: 12px; background: rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 6px;">
                <input type="checkbox" id="route-toggle-${r.replace(/ /g,'-')}" ${isChecked} style="width: 16px; height: 16px; cursor: pointer;">
                <label for="route-toggle-${r.replace(/ /g,'-')}" style="cursor: pointer;">${translateRoute(r)}</label>
            </div>
        `);
    });

    document.getElementById('save-hubs-btn').addEventListener('click', () => {
        let updated = {};
        globalHubs.forEach(h => {
            let val = document.getElementById(`hub-input-${h.id.replace(' ','')}`).value.trim();
            if (val) updated[h.id] = val;
        });
        appConfig.hubNames = updated;
        
        let ign = {};
        routesSet.forEach(r => {
            let cb = document.getElementById(`route-toggle-${r.replace(/ /g,'-')}`);
            if(cb && !cb.checked) ign[r] = true;
        });
        appConfig.ignoredRoutes = ign;
        
        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(appConfig)
        }).then(() => {
            alert("Configuration saved to MongoDB! The dashboard will now reflect these names and active routes globally.");
            location.reload();
        });
    });

    const delSelectedBtn = document.getElementById('delete-selected-hubs-btn');
    if (delSelectedBtn) {
        delSelectedBtn.addEventListener('click', () => {
            let selected = document.querySelectorAll('.hub-delete-cb:checked');
            if (selected.length === 0) {
                alert("Please select at least one hub to delete.");
                return;
            }
            if (confirm(`Are you sure you want to delete the ${selected.length} selected hub(s)?`)) {
                if (!appConfig.ignoredHubs) appConfig.ignoredHubs = [];
                let changed = false;
                selected.forEach(cb => {
                    let id = cb.getAttribute('data-id');
                    if (!appConfig.ignoredHubs.includes(id)) {
                        appConfig.ignoredHubs.push(id);
                        changed = true;
                    }
                });
                if (changed) {
                    fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ignoredHubs: appConfig.ignoredHubs })
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    location.reload();
                }
            }
        });
    }
}

function initKPIs(kpis) {
    animateValue(document.getElementById("kpi-buses"), 0, kpis.activeBuses, 1000);
    animateValue(document.getElementById("kpi-journeys"), 0, kpis.monitoredJourneys, 1000);
    animateValue(document.getElementById("kpi-anomalies"), 0, kpis.anomaliesDetected, 1000);
    animateValue(document.getElementById("kpi-hotspots"), 0, kpis.delayHotspots, 1000);
}

function animateValue(obj, start, end, duration) {
    if (!obj) return;
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        obj.innerHTML = Math.floor(progress * (end - start) + start);
        if (progress < 1) { window.requestAnimationFrame(step); }
    };
    window.requestAnimationFrame(step);
}

function getHaversine(lat1, lon1, lat2, lon2) {
    const R = 6371; 
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

let globalHotspotMap;
function initGlobalMap(hotspots) {
    globalHotspotMap = createMapWithLayers('map', [20.9042, 74.7749], 6);

    const hotspotIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `<div style='background-color:rgba(239, 68, 68, 0.6); width:20px; height:20px; border-radius:50%; box-shadow: 0 0 15px rgba(239, 68, 68, 0.8); border: 2px solid #ef4444;'></div>`,
        iconSize: [20, 20], iconAnchor: [10, 10]
    });

    hotspots.forEach(spot => {
        L.marker([spot.lat, spot.lon], {icon: hotspotIcon})
            .addTo(globalHotspotMap)
            .bindPopup(`<b>Delay Hotspot</b><br>${spot.desc}<br>Intensity: ${spot.intensity}`);
    });

    const routeFilter = document.getElementById('poi-filter-route');
    const busFilter = document.getElementById('poi-filter-bus');
    let routes = new Set();
    let buses = new Set();
    globalTrajectories.forEach(t => {
        routes.add(t.route);
        buses.add(t.bus_no);
    });
    
    routeFilter.innerHTML = '<option value="All">All Routes</option>';
    routes.forEach(r => routeFilter.insertAdjacentHTML('beforeend', `<option value="${r}">${translateRoute(r)}</option>`));
    busFilter.innerHTML = '<option value="All">All Buses</option>';
    buses.forEach(b => busFilter.insertAdjacentHTML('beforeend', `<option value="${b}">${b}</option>`));

    const toggleBtn = document.getElementById('toggleMapBtn');
    const mapSection = document.getElementById('view-hotspots');
    toggleBtn.addEventListener('click', () => {
        mapSection.classList.toggle('fullscreen');
        if (mapSection.classList.contains('fullscreen')) {
            toggleBtn.innerHTML = '<i class="ri-fullscreen-exit-line"></i>';
        } else {
            toggleBtn.innerHTML = '<i class="ri-fullscreen-line"></i>';
        }
        setTimeout(() => globalHotspotMap.invalidateSize(), 300);
    });

    globalHotspotMap.on('click', function(e) {
        const clickLat = e.latlng.lat;
        const clickLon = e.latlng.lng;
        
        const filterRoute = document.getElementById('poi-filter-route').value;
        const filterBus = document.getElementById('poi-filter-bus').value;
        
        let matchingJourneys = [];
        
        globalTrajectories.forEach(traj => {
            if (filterRoute !== 'All' && traj.route !== filterRoute) return;
            if (filterBus !== 'All' && traj.bus_no !== filterBus) return;
            
            for (let pt of traj.path) {
                if (getHaversine(clickLat, clickLon, pt[0], pt[1]) <= 0.5) { 
                    matchingJourneys.push({
                        date: traj.date,
                        bus_no: traj.bus_no,
                        route: translateRoute(traj.route),
                        duration: pt[2],
                        timestamp: pt[3]
                    });
                    break;
                }
            }
        });
        
        const container = document.getElementById('poi-analysis-container');
        
        if (matchingJourneys.length === 0) {
            container.style.display = 'none';
            L.popup()
                .setLatLng(e.latlng)
                .setContent(`<div style="font-family:'Outfit',sans-serif; color:#333;"><b>Dynamic POI ETA</b><hr style="margin:6px 0; border:none; border-top:1px solid #ccc;">No historical journeys found within 500m of this pin matching filters.</div>`)
                .openOn(globalHotspotMap);
            return;
        }
        
        container.style.display = 'block';
        
        let avgDuration = matchingJourneys.reduce((a, b) => a + b.duration, 0) / matchingJourneys.length;
        let maxDuration = Math.max(...matchingJourneys.map(j => j.duration));
        
        let totalMins = 0;
        matchingJourneys.forEach(j => {
            let d = new Date(j.timestamp * 1000);
            let istTime = new Date(d.getTime() + (5.5 * 60 * 60 * 1000));
            totalMins += (istTime.getUTCHours() * 60) + istTime.getUTCMinutes();
        });
        let avgTimeMins = totalMins / matchingJourneys.length;
        let avgH = Math.floor(avgTimeMins / 60) % 24;
        let avgM = Math.round(avgTimeMins % 60);
        let ampm = avgH >= 12 ? 'PM' : 'AM';
        let displayH = avgH % 12 || 12;
        
        document.getElementById('poi-avg-timeofday').innerText = `${displayH.toString().padStart(2, '0')}:${avgM.toString().padStart(2, '0')} ${ampm}`;
        document.getElementById('poi-avg-time').innerText = `${Math.floor(avgDuration/60)}h ${Math.round(avgDuration%60)}m`;
        document.getElementById('poi-max-time').innerText = `${Math.floor(maxDuration/60)}h ${Math.round(maxDuration%60)}m`;
        
        const tbody = document.getElementById('poi-table-body');
        tbody.innerHTML = '';
        
        matchingJourneys.sort((a, b) => new Date(a.date) - new Date(b.date));
        
        matchingJourneys.forEach(j => {
            const isWorst = j.duration === maxDuration;
            const rowStyle = isWorst ? 'background: rgba(239, 68, 68, 0.15);' : '';
            const textClass = isWorst ? 'color: #ef4444; font-weight: 600;' : '';
            
            let d = new Date(j.timestamp * 1000);
            let timeStr = d.toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit'});
            
            const tr = document.createElement('tr');
            tr.style.cssText = rowStyle;
            tr.innerHTML = `
                <td style="${textClass}">${j.date}</td>
                <td style="${textClass}"><i class="ri-bus-line"></i> ${j.bus_no}</td>
                <td style="${textClass}">${j.route}</td>
                <td style="${textClass}">${timeStr}</td>
                <td style="${textClass}">${Math.floor(j.duration/60)}h ${j.duration%60}m ${isWorst ? ' <i class="ri-alert-line"></i> (Worst)' : ''}</td>
            `;
            tbody.appendChild(tr);
        });
        
        L.popup().setLatLng(e.latlng).setContent(`<div style="font-family:'Outfit',sans-serif; color:#333; font-weight:600;">Analysis complete! Table loaded below.</div>`).openOn(globalHotspotMap);
        
        setTimeout(() => {
            container.scrollIntoView({behavior: 'smooth', block: 'end'});
        }, 300);
    });

    document.getElementById('poi-clear-filters').addEventListener('click', () => {
        document.getElementById('poi-filter-route').value = 'All';
        document.getElementById('poi-filter-bus').value = 'All';
        document.getElementById('poi-analysis-container').style.display = 'none';
        globalHotspotMap.closePopup();
    });
}

// TEMPORAL ANALYSIS
let temporalChartInst = null;
function initTemporalAnalysis() {
    const routeFilter = document.getElementById('temporal-filter-route');
    const busFilter = document.getElementById('temporal-filter-bus');
    
    if (!routeFilter || !busFilter || rawTemporalData.length === 0) return;

    let routes = new Set();
    let buses = new Set();
    rawTemporalData.forEach(t => {
        routes.add(t.route);
        buses.add(t.bus_no);
    });
    
    routeFilter.innerHTML = '<option value="All">All Routes</option>';
    routes.forEach(r => routeFilter.insertAdjacentHTML('beforeend', `<option value="${r}">${translateRoute(r)}</option>`));
    busFilter.innerHTML = '<option value="All">All Buses</option>';
    buses.forEach(b => busFilter.insertAdjacentHTML('beforeend', `<option value="${b}">${b}</option>`));

    const drawChart = () => {
        const fr = routeFilter.value;
        const fb = busFilter.value;
        
        let filtered = rawTemporalData.filter(t => {
            if (fr !== 'All' && t.route !== fr) return false;
            if (fb !== 'All' && t.bus_no !== fb) return false;
            return true;
        });

        let daySums = {0:[], 1:[], 2:[], 3:[], 4:[], 5:[], 6:[]};
        filtered.forEach(t => { daySums[t.day].push(t.duration); });

        let finalData = [];
        for(let i=0; i<7; i++) {
            let arr = daySums[i];
            finalData.push(arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0);
        }

        const ctx = document.getElementById('temporalChart').getContext('2d');
        if (temporalChartInst) temporalChartInst.destroy();

        temporalChartInst = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
                datasets: [{
                    label: 'Avg Duration (Hours)',
                    data: finalData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#a0aec0' } } },
                scales: {
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#a0aec0' } },
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#a0aec0' } }
                }
            }
        });
    };

    routeFilter.addEventListener('change', drawChart);
    busFilter.addEventListener('change', drawChart);
    drawChart(); // initial draw
}

let anomaliesMap;
function initAnomaliesMap() {
    anomaliesMap = createMapWithLayers('anomalies-map', [22.7196, 75.8577], 6);
}

let etaMap;
function initETAModels(predictions) {
    const list = document.getElementById('eta-list');
    if(!list) return;
    list.innerHTML = '';
    
    etaMap = createMapWithLayers('eta-map', [22.7196, 75.8577], 5);
    
    let allPaths = [];
    globalTrajectories.forEach(t => {
        const latlngs = t.path.map(p => [p[0], p[1]]);
        // By setting opacity extremely low, heavily stacked/travelled paths will naturally compound into a bright, saturated line.
        L.polyline(latlngs, {color: '#0ea5e9', weight: 4, opacity: 0.08}).addTo(etaMap);
        allPaths.push(...latlngs);
    });
    if(allPaths.length) etaMap.fitBounds(L.latLngBounds(allPaths));
    
    const toggleEtaBtn = document.getElementById('toggleEtaMapBtn');
    const etaSection = document.getElementById('view-eta');
    if (toggleEtaBtn) {
        toggleEtaBtn.addEventListener('click', () => {
            etaSection.classList.toggle('fullscreen');
            if (etaSection.classList.contains('fullscreen')) {
                toggleEtaBtn.innerHTML = '<i class="ri-fullscreen-exit-line"></i>';
            } else {
                toggleEtaBtn.innerHTML = '<i class="ri-fullscreen-line"></i>';
            }
            setTimeout(() => etaMap.invalidateSize(), 300);
        });
    }
    
    if(!predictions) return;
    predictions.forEach(p => {
        let badgeColor = p.status === 'Delayed' ? 'var(--accent-red)' : 'var(--primary)';
        list.innerHTML += `
            <div style="display: flex; justify-content: space-between; padding: 12px; background: rgba(255,255,255,0.05); margin-bottom: 8px; border-radius: 8px;">
                <div>
                    <h4>${translateRoute(p.route)}</h4>
                    <span style="font-size: 12px; color: var(--text-muted);">Avg Travel Time: ${p.avg_eta_hours}h</span>
                </div>
                <div style="color: ${badgeColor}; font-weight: 600;">${p.status}</div>
            </div>
        `;
    });
}

function renderAnomaliesTable() {
    const tbody = document.getElementById("anomalies-body");
    if(!tbody) return;
    tbody.innerHTML = '';

    let grouped = {};
    globalAnomaliesData.forEach(a => {
        if(!grouped[a.bus_no]) grouped[a.bus_no] = { bus_no: a.bus_no, route: translateRoute(a.route), stops: 0, total_duration: 0 };
        grouped[a.bus_no].stops += 1;
        grouped[a.bus_no].total_duration += a.duration_mins;
    });

    Object.values(grouped).forEach(g => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><span class="bus-row-link" onclick="focusBusOnAnomaliesMap('${g.bus_no}')"><i class="ri-bus-line"></i> ${g.bus_no}</span></td>
            <td>${g.route || 'Unknown'}</td>
            <td><span style="background:rgba(255,255,255,0.1); padding: 4px 8px; border-radius: 4px;">${g.stops} Stops</span></td>
            <td><strong style="color:var(--accent-orange);">${g.total_duration} mins</strong></td>
            <td><button class="btn-sm btn-view-map" onclick="focusBusOnAnomaliesMap('${g.bus_no}')"><i class="ri-map-pin-line"></i> View on Map</button></td>
        `;
        tbody.appendChild(tr);
    });
}

function focusBusOnAnomaliesMap(busNo) {
    document.querySelectorAll('.view-section').forEach(sec => sec.style.display = 'none');
    const anomaliesView = document.getElementById('view-anomalies');
    anomaliesView.style.display = 'flex';
    
    document.querySelectorAll('.nav-menu a').forEach(l => l.classList.remove('active'));
    let navItem = document.querySelector('.nav-menu [data-view="anomalies"]');
    if (navItem) navItem.classList.add('active');

    const busAnomalies = globalAnomaliesData.filter(a => a.bus_no === busNo);
    if (busAnomalies.length === 0) return;

    anomalyMarkers.forEach(m => anomaliesMap.removeLayer(m));
    anomalyMarkers = [];

    const busIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `<div style='background-color:#3b82f6; width:16px; height:16px; border-radius:50%; border:2px solid #fff; box-shadow: 0 0 10px #3b82f6;'></div>`,
        iconSize: [16, 16]
    });

    setTimeout(() => {
        anomaliesMap.invalidateSize();
        anomaliesView.scrollIntoView({behavior: 'smooth', block: 'start'});
        
        busAnomalies.forEach(a => {
            const marker = L.marker([a.lat, a.lon], {icon: busIcon}).addTo(anomaliesMap);
            marker.bindPopup(`<b>Bus ${busNo} Anomaly</b><br>Duration: ${a.duration_mins} mins<br>Risk: ${a.risk}`);
            anomalyMarkers.push(marker);
        });

        const group = new L.featureGroup(anomalyMarkers);
        anomaliesMap.fitBounds(group.getBounds().pad(0.1));
    }, 200);
}

// --- SAFE ZONES / GEOFENCE LOGIC ---
const Dashboard = {
    geofenceMap: null,
    tempMarker: null,
    
    initGeofenceMap() {
        this.geofenceMap = createMapWithLayers('geofence-map', [22.7196, 75.8577], 6);

        this.renderSafeZonesOnMap();

        this.geofenceMap.on('click', (e) => {
            if (this.tempMarker) this.geofenceMap.removeLayer(this.tempMarker);
            
            const pulseIcon = L.divIcon({
                className: 'pulse-icon-wrapper',
                html: `<div class="pin-pulse"></div><div class="pin-marker"><i class="ri-map-pin-fill"></i></div>`,
                iconSize: [40, 40],
                iconAnchor: [20, 36]
            });

            this.tempMarker = L.marker(e.latlng, {icon: pulseIcon}).addTo(this.geofenceMap);
            
            setTimeout(() => {
                const modal = document.getElementById('safe-zone-modal');
                modal.classList.add('show');
                document.getElementById('sz-lat').value = e.latlng.lat.toFixed(5);
                document.getElementById('sz-lon').value = e.latlng.lng.toFixed(5);
            }, 600);
        });

        document.getElementById('sz-cancel').addEventListener('click', () => {
            document.getElementById('safe-zone-modal').classList.remove('show');
            if (this.tempMarker) this.geofenceMap.removeLayer(this.tempMarker);
        });

        document.getElementById('sz-save').addEventListener('click', () => {
            const name = document.getElementById('sz-name').value;
            const type = document.getElementById('sz-type').value;
            const lat = document.getElementById('sz-lat').value;
            const lon = document.getElementById('sz-lon').value;

            if(!name) { alert("Please provide a name."); return; }

            let newZone = { id: `sz_${Date.now()}`, name, type, lat: parseFloat(lat), lon: parseFloat(lon) };
            safeZonesData.push(newZone);
            if(!appConfig.safeZones) appConfig.safeZones = [];
            appConfig.safeZones.push(newZone);
            
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ safeZones: appConfig.safeZones })
            }).then(() => {
                document.getElementById('safe-zone-modal').classList.remove('show');
                this.renderSafeZonesList();
                this.renderSafeZonesOnMap();
            });
        });
    },

    renderSafeZonesList() {
        const list = document.getElementById('safe-zones-list');
        list.innerHTML = '';
        safeZonesData.forEach(sz => {
            let icon = 'ri-shield-check-line';
            if(sz.type === 'fuel') icon = 'ri-gas-station-fill';
            if(sz.type === 'parking') icon = 'ri-parking-box-fill';

            list.innerHTML += `
                <div class="whitelist-item">
                    <div class="whitelist-icon"><i class="${icon}"></i></div>
                    <div class="whitelist-details">
                        <h4>${sz.name}</h4>
                        <p>${sz.lat.toFixed(3)}, ${sz.lon.toFixed(3)}</p>
                    </div>
                </div>
            `;
        });
    },

    renderSafeZonesOnMap() {
        safeZonesData.forEach(sz => {
            const circle = L.circle([sz.lat, sz.lon], {
                color: '#10b981',
                fillColor: '#10b981',
                fillOpacity: 0.2,
                radius: 1000
            }).addTo(this.geofenceMap);
            circle.bindPopup(`<b>${sz.name}</b><br>Type: ${sz.type}<br>Protected Radius: 1km`);
        });
    }
};

window.deleteHub = function(hubId) {
    if(confirm("Are you sure you want to delete this Hub? All routes connected to it will be hidden from the dashboard.")) {
        if(!appConfig.ignoredHubs) appConfig.ignoredHubs = [];
        if(!appConfig.ignoredHubs.includes(hubId)) {
            appConfig.ignoredHubs.push(hubId);
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ignoredHubs: appConfig.ignoredHubs })
            }).then(() => {
                alert("Hub deleted from DB. The dashboard will now reload.");
                location.reload();
            });
        }
    }
};

window.saveHubNameFromPopup = function(hubId) {
    let val = document.getElementById(`popup-input-${hubId.replace(' ','')}`).value.trim();
    if(val) {
        let savedHubs = appConfig.hubNames || {};
        savedHubs[hubId] = val;
        localStorage.setItem('hubNames', JSON.stringify(savedHubs));
        alert("Hub name saved! Dashboard will now reload.");
        location.reload();
    }
};
