import re

file_path = r'c:\Users\PC\Desktop\DL\dashboard\script.js'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add appConfig at the top
content = re.sub(
    r'(let rawTemporalData = \[\];)',
    r'\1\nlet appConfig = { hubNames: {}, ignoredRoutes: {}, ignoredHubs: [], safeZones: [] };',
    content
)

# 2. Update translateRoute
content = re.sub(
    r"let savedHubs = JSON\.parse\(localStorage\.getItem\('hubNames'\) \|\| '\{\}'\);",
    r"let savedHubs = appConfig.hubNames || {};",
    content
)

# 3. Update DOMContentLoaded fetch logic
old_fetch = r"""    fetch\('data\.json'\)
        \.then\(response => response\.json\(\)\)
        \.then\(data => \{
            let ignoredRoutes = JSON\.parse\(localStorage\.getItem\('ignoredRoutes'\) \|\| '\{\}'\);
            let ignoredHubs = JSON\.parse\(localStorage\.getItem\('ignoredHubs'\) \|\| '\[\]'\);"""

new_fetch = r"""    Promise.all([
        fetch('/api/config').then(r => r.json()).catch(() => ({ hubNames: {}, ignoredRoutes: {}, ignoredHubs: [], safeZones: [] })),
        fetch('data.json').then(r => r.json())
    ]).then(([configData, data]) => {
            appConfig = configData;
            let ignoredRoutes = appConfig.ignoredRoutes || {};
            let ignoredHubs = appConfig.ignoredHubs || [];
            
            // Merge safe zones from DB with any from data.json
            let combinedSafeZones = [...(data.safeZones || [])];
            let dbSafeZones = appConfig.safeZones || [];
            let existingSzIds = new Set(combinedSafeZones.map(s => s.id));
            dbSafeZones.forEach(sz => { if(!existingSzIds.has(sz.id)) combinedSafeZones.push(sz); });
            data.safeZones = combinedSafeZones;"""

content = re.sub(old_fetch, new_fetch, content)

# 4. initHubConfig - savedHubs
content = re.sub(
    r"let savedHubs = JSON\.parse\(localStorage\.getItem\('hubNames'\) \|\| '\{\}'\);",
    r"let savedHubs = appConfig.hubNames || {};",
    content
)

# 5. initHubConfig - ignoredRoutes
content = re.sub(
    r"let savedRoutes = JSON\.parse\(localStorage\.getItem\('ignoredRoutes'\) \|\| '\{\}'\);",
    r"let savedRoutes = appConfig.ignoredRoutes || {};",
    content
)

# 6. Save configuration logic inside initHubConfig
old_save_btn = r"""        localStorage\.setItem\('hubNames', JSON\.stringify\(updated\)\);
        
        let ign = \{\};
        routesSet\.forEach\(r => \{
            let cb = document\.getElementById\(`route-toggle-\$\{r\.replace\(/ /g,'-'\)\}`\);
            if\(cb && !cb\.checked\) ign\[r\] = true;
        \}\);
        localStorage\.setItem\('ignoredRoutes', JSON\.stringify\(ign\)\);
        
        alert\("Configuration saved! The dashboard will now reflect these names and active routes globally\."\);
        location\.reload\(\); """

new_save_btn = r"""        appConfig.hubNames = updated;
        
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
        });"""
content = re.sub(old_save_btn, new_save_btn, content)

# 7. Geofence save logic
old_geofence_save = r"""            safeZonesData\.push\(\{ id: `sz_\$\{Date\.now\(\)\}`, name, type, lat: parseFloat\(lat\), lon: parseFloat\(lon\) \}\);
            
            document\.getElementById\('safe-zone-modal'\)\.classList\.remove\('show'\);
            this\.renderSafeZonesList\(\);
            this\.renderSafeZonesOnMap\(\);"""

new_geofence_save = r"""            let newZone = { id: `sz_${Date.now()}`, name, type, lat: parseFloat(lat), lon: parseFloat(lon) };
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
            });"""
content = re.sub(old_geofence_save, new_geofence_save, content)

# 8. window.deleteHub
old_delete_hub = r"""window\.deleteHub = function\(hubId\) \{
    if\(confirm\("Are you sure you want to delete this Hub\? All routes connected to it will be hidden from the dashboard\."\)\) \{
        let ignoredHubs = JSON\.parse\(localStorage\.getItem\('ignoredHubs'\) \|\| '\[\]'\);
        if\(!ignoredHubs\.includes\(hubId\)\) \{
            ignoredHubs\.push\(hubId\);
            localStorage\.setItem\('ignoredHubs', JSON\.stringify\(ignoredHubs\)\);
        \}
        alert\("Hub deleted\. The dashboard will now reload\."\);
        location\.reload\(\);
    \}
\};"""

new_delete_hub = r"""window.deleteHub = function(hubId) {
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
};"""
content = re.sub(old_delete_hub, new_delete_hub, content)

# 9. window.saveHubNameFromPopup
old_popup_save = r"""window\.saveHubNameFromPopup = function\(hubId\) \{
    let val = document\.getElementById\(`popup-input-\$\{hubId\.replace\(' ',''\)\}`\)\.value\.trim\(\);
    if\(val\) \{
        let savedHubs = JSON\.parse\(localStorage\.getItem\('hubNames'\) \|\| '\{\}'\);
        savedHubs\[hubId\] = val;
        localStorage\.setItem\('hubNames', JSON\.stringify\(savedHubs\)\);
        alert\("Hub name saved! Dashboard will now reload\."\);
        location\.reload\(\);
    \}
\};"""

new_popup_save = r"""window.saveHubNameFromPopup = function(hubId) {
    let val = document.getElementById(`popup-input-${hubId.replace(' ','')}`).value.trim();
    if(val) {
        if(!appConfig.hubNames) appConfig.hubNames = {};
        appConfig.hubNames[hubId] = val;
        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hubNames: appConfig.hubNames })
        }).then(() => {
            alert("Hub name saved to DB! Dashboard will now reload.");
            location.reload();
        });
    }
};"""
content = re.sub(old_popup_save, new_popup_save, content)


with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated script.js")
