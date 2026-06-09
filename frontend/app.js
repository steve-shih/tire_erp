// app.js

const API_BASE = window.location.origin + "/api";
let currentToken = localStorage.getItem("token");

// ==================== Initialization & Auth ====================
document.addEventListener("DOMContentLoaded", () => {
    if (currentToken) {
        checkAuth();
    } else {
        document.getElementById("login-screen").classList.remove("hidden");
    }

    // Login Form
    document.getElementById("login-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const u = document.getElementById("login-username").value;
        const p = document.getElementById("login-password").value;
        try {
            const res = await fetch(`${API_BASE}/login`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username: u, password: p})
            });
            if (res.ok) {
                const data = await res.json();
                currentToken = data.access_token;
                localStorage.setItem("token", currentToken);
                document.getElementById("login-error").classList.add("hidden");
                checkAuth();
            } else {
                document.getElementById("login-error").classList.remove("hidden");
            }
        } catch (err) {
            console.error(err);
            document.getElementById("login-error").classList.remove("hidden");
        }
    });

    // Logout
    document.getElementById("logout-btn")?.addEventListener("click", () => {
        localStorage.removeItem("token");
        location.reload();
    });

    // Navigation setup
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", (e) => {
            const target = e.currentTarget.getAttribute("data-target");
            window.app.navigate(target);
        });
    });
});

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/me`, { headers: authHeaders() });
        if (res.ok) {
            const user = await res.json();
            document.getElementById("login-screen").classList.add("hidden");
            document.getElementById("app").classList.remove("hidden");
            document.getElementById("current-user-display").innerText = `登入者: ${user.username ?? ''} (${user.role === 'owner' ? '老闆' : '員工'})`;
            
            // Handle RBAC UI
            if (user.role === 'owner') {
                document.getElementById("owner-settings-group").classList.remove("hidden");
                // Owners see all by default, no need to hide
            } else {
                document.getElementById("owner-settings-group").classList.add("hidden");
            }
            
            // Load permissions and apply to sidebar
            await applyPermissions(user.role);

            // Load initial data
            loadAnnouncements();
            window.app.navigate("sales-section");
        } else {
            throw new Error("Invalid token");
        }
    } catch (err) {
        localStorage.removeItem("token");
        document.getElementById("login-screen").classList.remove("hidden");
    }
}

async function applyPermissions(role) {
    try {
        const data = await apiGet("/settings/permissions");
        const visible = data.staff_visible_menus || [];
        
        if (role === 'owner') {
            // Check the checkboxes in settings page for owners
            document.querySelectorAll('input[name="perm_menu"]').forEach(cb => {
                cb.checked = visible.includes(cb.value);
            });
            // Show all nav items for owners
            document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("hidden"));
        } else {
            // Hide nav items staff is not allowed to see
            document.querySelectorAll(".nav-item").forEach(n => {
                const target = n.getAttribute("data-target");
                if (target && target !== 'settings-section') {
                    if (!visible.includes(target)) {
                        n.classList.add("hidden");
                    } else {
                        n.classList.remove("hidden");
                    }
                }
            });
        }
    } catch(e) { console.error("Error loading permissions", e); }
}

async function savePermissions() {
    const checked = [];
    document.querySelectorAll('input[name="perm_menu"]:checked').forEach(cb => {
        checked.push(cb.value);
    });
    try {
        await apiPut("/settings/permissions", { staff_visible_menus: checked });
        alert("權限儲存成功！下次員工登入時生效。");
    } catch(e) {
        alert("儲存失敗: " + e.message);
    }
}

function authHeaders() {
    return { "Authorization": `Bearer ${currentToken}`, "Content-Type": "application/json" };
}

// ==================== Navigation & Global App State ====================
window.app = {
    currentSection: "sales-section",
    navigate: function(sectionId) {
        // Update nav UI
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        const targetNav = document.querySelector(`.nav-item[data-target="${sectionId}"]`);
        if (targetNav) targetNav.classList.add("active");

        // Hide all sections, show target
        document.querySelectorAll(".app-section").forEach(s => s.classList.add("hidden"));
        document.getElementById(sectionId).classList.remove("hidden");
        this.currentSection = sectionId;

        // Trigger load
        if (sectionId === "sales-section") loadSalesOrders();
        else if (sectionId === "quotes-section") loadQuotes();
        else if (sectionId === "inventory-section") loadInventory();
        else if (sectionId === "purchases-section") loadPurchases();
        else if (sectionId === "customers-section") loadCustomers();
        else if (sectionId === "vendors-section") loadVendors();
        else if (sectionId === "ar-section") { switchArTab('summary'); }
        else if (sectionId === "ap-section") { switchApTab('summary'); }
        else if (sectionId === "notes-section") loadNotes();
        else if (sectionId === "reports-section") initReports();
        else if (sectionId === "payroll-section") { switchPayrollTab('emp'); }
        else if (sectionId === "users-section") loadUsers();
        else if (sectionId === "logs-section") loadLogs();
    }
};

// ==================== API Helpers ====================
async function apiGet(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiPost(endpoint, data) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST", headers: authHeaders(), body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiPut(endpoint, data) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "PUT", headers: authHeaders(), body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiDelete(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "DELETE", headers: authHeaders()
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ==================== Modals ====================
function openModal(id) {
    document.getElementById(id).classList.add("active");
}
function closeModal(id) {
    document.getElementById(id).classList.remove("active");
}

// ==================== AutoComplete ====================
// A simple generic autocomplete
let searchDebounce;
document.getElementById("order-party-search")?.addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => handlePartySearch(e.target.value), 300);
});

async function handlePartySearch(query) {
    const list = document.getElementById("order-party-list");
    if (!query) { list.style.display = "none"; return; }
    
    const type = document.getElementById("order-type").value;
    const endpoint = (type === 'purchase' || type === 'quote-vendor') ? 'vendors' : 'customers';
    
    try {
        const result = await apiGet(`/${endpoint}?search=${encodeURIComponent(query)}`);
        const data = result.data;
        list.innerHTML = "";
        if (data.length === 0) { list.style.display = "none"; return; }
        
        data.forEach(item => {
            const id = item.customer_id || item.vendor_id;
            const div = document.createElement("div");
            div.className = "autocomplete-item";
            div.innerHTML = `<div>${item.name ?? ''} <span class="badge badge-secondary">${id}</span></div>
                             <div class="autocomplete-detail">${item.phone || ''} | ${item.address || ''}</div>`;
            div.onclick = () => selectParty(item);
            list.appendChild(div);
        });
        list.style.display = "block";
    } catch (e) { console.error(e); }
}

function selectParty(item) {
    document.getElementById("op-id").value = item.customer_id || item.vendor_id;
    document.getElementById("op-name").value = item.name;
    document.getElementById("op-taxid").value = item.uniform_number || "";
    document.getElementById("op-phone").value = item.phone || "";
    document.getElementById("op-address").value = item.address || "";
    
    document.getElementById("order-party-search").value = "";
    document.getElementById("order-party-list").style.display = "none";
}

// Close autocomplete on click outside
document.addEventListener("click", (e) => {
    if (!e.target.closest('.autocomplete-wrapper')) {
        const list = document.getElementById("order-party-list");
        if(list) list.style.display = "none";
    }
});


// ==================== Dynamic Line Items ====================
let lineItemCount = 0;
function addLineItem(data = null) {
    const tbody = document.getElementById("line-items-body");
    const idx = lineItemCount++;
    const tr = document.createElement("tr");
    tr.id = `line-${idx}`;
    
    tr.innerHTML = `
        <td><input type="text" class="form-control" name="item_code" onchange="lookupProduct(this, ${idx})" required value="${data ? data.product_code : ''}"></td>
        <td>
            <input type="text" class="form-control mb-1" name="item_brand" placeholder="品牌" value="${data && data.brand ? data.brand : ''}">
            <div class="flex gap-2 mb-1">
                <input type="text" class="form-control" name="item_spec" placeholder="規格" value="${data && data.spec ? data.spec : ''}">
                <input type="text" class="form-control" name="item_pattern" placeholder="花紋" value="${data && data.pattern ? data.pattern : ''}">
            </div>
            <div class="item-stock-info text-xs" style="font-size: 12px; color: #3b82f6; display: none;"></div>
        </td>
        <td><input type="number" class="form-control" name="item_qty" oninput="calcLineAmount(${idx})" required min="1" value="${data ? data.qty : '1'}"></td>
        <td><input type="number" class="form-control" name="item_price" oninput="calcLineAmount(${idx})" required value="${data ? data.price : '0'}"></td>
        <td><input type="number" class="form-control" name="item_amount" readonly value="${data ? data.amount : '0'}"></td>
        <td>
            <input type="text" class="form-control mb-1" name="item_pos" placeholder="部位(例: FL,FR)" value="${data && data.tire_position ? data.tire_position : ''}" readonly>
            <input type="text" class="form-control" name="item_srv" placeholder="維修(例: 換新胎)" value="${data && data.service_type ? data.service_type : ''}">
        </td>
        <td><button type="button" class="btn btn-danger btn-sm btn-icon" onclick="removeLineItem(${idx})"><i class="fas fa-trash"></i></button></td>
    `;
    tbody.appendChild(tr);
    calcOrderTotal();
}

function removeLineItem(idx) {
    const tr = document.getElementById(`line-${idx}`);
    if (tr) {
        tr.remove();
        calcOrderTotal();
    }
}

async function lookupProduct(inputEl, idx) {
    const code = inputEl.value.trim();
    if (!code) return;
    try {
        const result = await apiGet(`/products?search=${encodeURIComponent(code)}`);
        const data = result.data;
        if (!data || !Array.isArray(data)) return;
        
        // Find exact match (case insensitive)
        const product = data.find(p => p.product_code && p.product_code.toLowerCase() === code.toLowerCase());
        if (product) {
            const tr = document.getElementById(`line-${idx}`);
            if (tr) {
                // Fill details
                tr.querySelector('input[name="item_brand"]').value = product.brand ?? '';
                tr.querySelector('input[name="item_spec"]').value = product.spec ?? '';
                tr.querySelector('input[name="item_pattern"]').value = product.pattern ?? '';
                
                // Show stock info
                const stockInfoDiv = tr.querySelector('.item-stock-info');
                if (stockInfoDiv) {
                    stockInfoDiv.innerText = `目前庫存量: ${product.stock_qty ?? 0}`;
                    stockInfoDiv.style.display = 'block';
                    
                    // If stock is insufficient, show warning
                    if ((product.stock_qty ?? 0) <= 0) {
                        stockInfoDiv.style.color = 'var(--danger)';
                        stockInfoDiv.innerHTML += ' <span style="font-weight: bold;">(庫存不足)</span>';
                    } else {
                        stockInfoDiv.style.color = '#3b82f6';
                    }
                }
                
                // Fill price based on order type
                const orderType = document.getElementById("order-type").value;
                const priceInput = tr.querySelector('input[name="item_price"]');
                if (priceInput) {
                    if (orderType === 'sales' || orderType === 'quote-customer') {
                        priceInput.value = product.price ?? 0;
                    } else {
                        priceInput.value = product.cost ?? 0;
                    }
                    calcLineAmount(idx);
                }
            }
        }
    } catch (e) {
        console.error("Error looking up product:", e);
    }
}

function calcLineAmount(idx) {
    const tr = document.getElementById(`line-${idx}`);
    if (!tr) return;
    const qty = parseFloat(tr.querySelector('input[name="item_qty"]').value) || 0;
    const price = parseFloat(tr.querySelector('input[name="item_price"]').value) || 0;
    const amt = qty * price;
    tr.querySelector('input[name="item_amount"]').value = amt;
    calcOrderTotal();
}

function calcOrderTotal() {
    let subtotal = 0;
    document.querySelectorAll('input[name="item_amount"]').forEach(el => {
        subtotal += parseFloat(el.value) || 0;
    });
    
    // Tax calculation
    const tax = Math.round(subtotal * 0.05); // Standard 5% tax
    const grand = subtotal + tax;
    
    document.getElementById("order-subtotal").innerText = subtotal;
    document.getElementById("order-tax").innerText = tax;
    document.getElementById("order-grandtotal").innerText = grand;
}


// ==================== TIRE POSITION SVG SELECTOR ====================
let currentTireTargetIdx = null;

function openTireSelector() {
    // Open modal to select tires. It will apply to the last focused line item, or we can just append text.
    // For simplicity, let's just use it to generate a string that the user can copy or we auto-fill to the last line.
    const tbody = document.getElementById("line-items-body");
    const rows = tbody.querySelectorAll("tr");
    if (rows.length === 0) {
        alert("請先新增一列明細"); return;
    }
    // Target the last row
    const lastRow = rows[rows.length - 1];
    currentTireTargetIdx = parseInt(lastRow.id.split("-")[1]);
    
    document.getElementById("selected-tire-positions").value = "";
    document.getElementById("tire-service-type").value = "換新胎";
    renderTireSvg();
    openModal('tire-modal');
}

function renderTireSvg() {
    const container = document.getElementById("tire-svg-container");
    const type = document.querySelector('input[name="vehicle_type"]:checked').value;
    
    let svg = '';
    if (type === 'sedan') {
        svg = `
            <svg class="tire-svg" viewBox="0 0 100 150">
                <rect x="20" y="20" width="60" height="110" fill="none" stroke="#64748b" stroke-width="2" rx="10"/>
                <!-- Wheels -->
                <rect class="tire-part" id="tire-FL" x="5" y="30" width="15" height="25" rx="3" onclick="toggleTire('FL')"/>
                <rect class="tire-part" id="tire-FR" x="80" y="30" width="15" height="25" rx="3" onclick="toggleTire('FR')"/>
                <rect class="tire-part" id="tire-RL" x="5" y="95" width="15" height="25" rx="3" onclick="toggleTire('RL')"/>
                <rect class="tire-part" id="tire-RR" x="80" y="95" width="15" height="25" rx="3" onclick="toggleTire('RR')"/>
                <text x="50" y="75" font-size="10" text-anchor="middle" fill="#64748b">CAR</text>
            </svg>
        `;
    } else if (type === 'truck') {
        svg = `
            <svg class="tire-svg" viewBox="0 0 120 200">
                <rect x="30" y="20" width="60" height="160" fill="none" stroke="#64748b" stroke-width="2" rx="5"/>
                <!-- Front (2) -->
                <rect class="tire-part" id="tire-FL" x="10" y="30" width="15" height="25" rx="3" onclick="toggleTire('FL')"/>
                <rect class="tire-part" id="tire-FR" x="95" y="30" width="15" height="25" rx="3" onclick="toggleTire('FR')"/>
                <!-- Middle (4) -->
                <rect class="tire-part" id="tire-ML1" x="10" y="90" width="10" height="25" rx="2" onclick="toggleTire('ML1')"/>
                <rect class="tire-part" id="tire-ML2" x="22" y="90" width="10" height="25" rx="2" onclick="toggleTire('ML2')"/>
                <rect class="tire-part" id="tire-MR1" x="88" y="90" width="10" height="25" rx="2" onclick="toggleTire('MR1')"/>
                <rect class="tire-part" id="tire-MR2" x="100" y="90" width="10" height="25" rx="2" onclick="toggleTire('MR2')"/>
                <!-- Rear (4) -->
                <rect class="tire-part" id="tire-RL1" x="10" y="140" width="10" height="25" rx="2" onclick="toggleTire('RL1')"/>
                <rect class="tire-part" id="tire-RL2" x="22" y="140" width="10" height="25" rx="2" onclick="toggleTire('RL2')"/>
                <rect class="tire-part" id="tire-RR1" x="88" y="140" width="10" height="25" rx="2" onclick="toggleTire('RR1')"/>
                <rect class="tire-part" id="tire-RR2" x="100" y="140" width="10" height="25" rx="2" onclick="toggleTire('RR2')"/>
                <text x="60" y="100" font-size="10" text-anchor="middle" fill="#64748b" transform="rotate(-90 60,100)">TRUCK</text>
            </svg>
        `;
    } else if (type === 'truck12') {
        svg = `
            <svg class="tire-svg" viewBox="0 0 120 220">
                <rect x="30" y="20" width="60" height="180" fill="none" stroke="#64748b" stroke-width="2" rx="5"/>
                <!-- Front Row 1 (2) -->
                <rect class="tire-part" id="tire-FL1" x="10" y="30" width="15" height="25" rx="3" onclick="toggleTire('FL1')"/>
                <rect class="tire-part" id="tire-FR1" x="95" y="30" width="15" height="25" rx="3" onclick="toggleTire('FR1')"/>
                <!-- Front Row 2 (2) -->
                <rect class="tire-part" id="tire-FL2" x="10" y="70" width="15" height="25" rx="3" onclick="toggleTire('FL2')"/>
                <rect class="tire-part" id="tire-FR2" x="95" y="70" width="15" height="25" rx="3" onclick="toggleTire('FR2')"/>
                <!-- Middle (4) -->
                <rect class="tire-part" id="tire-ML1" x="10" y="120" width="10" height="25" rx="2" onclick="toggleTire('ML1')"/>
                <rect class="tire-part" id="tire-ML2" x="22" y="120" width="10" height="25" rx="2" onclick="toggleTire('ML2')"/>
                <rect class="tire-part" id="tire-MR1" x="88" y="120" width="10" height="25" rx="2" onclick="toggleTire('MR1')"/>
                <rect class="tire-part" id="tire-MR2" x="100" y="120" width="10" height="25" rx="2" onclick="toggleTire('MR2')"/>
                <!-- Rear (4) -->
                <rect class="tire-part" id="tire-RL1" x="10" y="170" width="10" height="25" rx="2" onclick="toggleTire('RL1')"/>
                <rect class="tire-part" id="tire-RL2" x="22" y="170" width="10" height="25" rx="2" onclick="toggleTire('RL2')"/>
                <rect class="tire-part" id="tire-RR1" x="88" y="170" width="10" height="25" rx="2" onclick="toggleTire('RR1')"/>
                <rect class="tire-part" id="tire-RR2" x="100" y="170" width="10" height="25" rx="2" onclick="toggleTire('RR2')"/>
                <text x="60" y="110" font-size="10" text-anchor="middle" fill="#64748b" transform="rotate(-90 60,110)">TRUCK</text>
            </svg>
        `;
    }
    container.innerHTML = svg;
}

const selectedTires = new Set();
function toggleTire(id) {
    const el = document.getElementById(`tire-${id}`);
    if (selectedTires.has(id)) {
        selectedTires.delete(id);
        el.classList.remove("selected");
    } else {
        selectedTires.add(id);
        el.classList.add("selected");
    }
    document.getElementById("selected-tire-positions").value = Array.from(selectedTires).join(",");
}

function confirmTireSelection() {
    if (currentTireTargetIdx !== null) {
        const tr = document.getElementById(`line-${currentTireTargetIdx}`);
        if (tr) {
            tr.querySelector('input[name="item_pos"]').value = document.getElementById("selected-tire-positions").value;
            tr.querySelector('input[name="item_srv"]').value = document.getElementById("tire-service-type").value;
            // Also update qty based on number of selected tires
            if(selectedTires.size > 0) {
                tr.querySelector('input[name="item_qty"]').value = selectedTires.size;
                calcLineAmount(currentTireTargetIdx);
            }
        }
    }
    selectedTires.clear();
    closeModal('tire-modal');
}


// ==================== Order Modal Logic ====================
function openOrderModal(type, existingData = null) {
    document.getElementById("order-form").reset();
    document.getElementById("line-items-body").innerHTML = "";
    lineItemCount = 0;
    document.getElementById("order-type").value = type;
    document.getElementById("order-id-input").value = "";
    
    // Auto generate ID
    const prefix = type === 'sales' ? 'SO' : (type === 'purchase' ? 'PO' : 'Q');
    document.getElementById("order-num").value = `${prefix}-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${Math.floor(Math.random()*1000)}`;
    document.getElementById("order-date").value = new Date().toISOString().split("T")[0];
    
    // UI adjustments based on type
    const titleMap = {
        'sales': '新增出貨單', 'purchase': '新增進貨單',
        'quote-customer': '新增客戶報價單', 'quote-vendor': '新增廠商報價單'
    };
    document.getElementById("order-modal-title").innerText = titleMap[type];
    
    const deptWrap = document.getElementById("order-dept-wrapper");
    if(type === 'purchase' || type === 'quote-vendor') {
        deptWrap.classList.add("hidden");
        document.getElementById("op-plate-wrapper").classList.add("hidden");
        document.getElementById("order-party-title").innerText = "廠商資料";
    } else {
        deptWrap.classList.remove("hidden");
        document.getElementById("op-plate-wrapper").classList.remove("hidden");
        document.getElementById("order-party-title").innerText = "客戶資料";
    }
    
    addLineItem(); // Start with one empty row
    calcOrderTotal();
    openModal('order-modal');
}

async function saveOrder() {
    // Gather data
    const type = document.getElementById("order-type").value;
    
    const items = [];
    document.querySelectorAll("#line-items-body tr").forEach(tr => {
        items.push({
            product_code: tr.querySelector('input[name="item_code"]').value,
            brand: tr.querySelector('input[name="item_brand"]').value,
            spec: tr.querySelector('input[name="item_spec"]').value,
            pattern: tr.querySelector('input[name="item_pattern"]').value,
            qty: parseInt(tr.querySelector('input[name="item_qty"]').value) || 0,
            price: parseFloat(tr.querySelector('input[name="item_price"]').value) || 0,
            amount: parseFloat(tr.querySelector('input[name="item_amount"]').value) || 0,
            tire_position: tr.querySelector('input[name="item_pos"]').value,
            service_type: tr.querySelector('input[name="item_srv"]').value
        });
    });
    
    if (items.length === 0) { alert("請至少新增一筆明細"); return; }
    
    const payload = {
        date: document.getElementById("order-date").value + "T00:00:00Z",
        total_amount: parseFloat(document.getElementById("order-subtotal").innerText),
        tax_amount: parseFloat(document.getElementById("order-tax").innerText),
        grand_total: parseFloat(document.getElementById("order-grandtotal").innerText),
        payment_status: document.getElementById("order-payment").value,
        invoice_number: document.getElementById("order-invoice").value,
        items: items
    };

    try {
        if (type === 'sales') {
            payload.order_id = document.getElementById("order-num").value;
            payload.category = document.getElementById("order-dept").value;
            payload.department = payload.category.includes('大車') ? 'truck' : 'sedan';
            payload.customer_id = document.getElementById("op-id").value;
            payload.customer_name = document.getElementById("op-name").value;
            payload.customer_uniform_number = document.getElementById("op-taxid").value;
            payload.customer_phone = document.getElementById("op-phone").value;
            payload.customer_address = document.getElementById("op-address").value;
            payload.plate_number = document.getElementById("op-plate").value;
            await apiPost('/sales', payload);
            loadSalesOrders();
        } else if (type === 'purchase') {
            payload.purchase_id = document.getElementById("order-num").value;
            payload.vendor_id = document.getElementById("op-id").value;
            payload.vendor_name = document.getElementById("op-name").value;
            payload.vendor_uniform_number = document.getElementById("op-taxid").value;
            payload.vendor_phone = document.getElementById("op-phone").value;
            payload.vendor_address = document.getElementById("op-address").value;
            await apiPost('/purchases', payload);
            loadPurchases();
        } else if (type.startsWith('quote')) {
            payload.quote_id = document.getElementById("order-num").value;
            payload.quote_type = type.split('-')[1]; // customer or vendor
            payload.category = document.getElementById("order-dept").value;
            payload.party_id = document.getElementById("op-id").value;
            payload.party_name = document.getElementById("op-name").value;
            payload.uniform_number = document.getElementById("op-taxid").value;
            payload.phone = document.getElementById("op-phone").value;
            payload.address = document.getElementById("op-address").value;
            if(payload.quote_type === 'customer') payload.plate_number = document.getElementById("op-plate").value;
            
            await apiPost('/quotes', payload);
            loadQuotes();
        }
        closeModal('order-modal');
    } catch (e) {
        alert("儲存失敗: " + e.message);
    }
}


// ==================== Data Loading (Main Sections) ====================
async function loadSalesOrders(page = 1) {
    const tbody = document.querySelector("#sales-table tbody");
    tbody.innerHTML = "<tr><td colspan='9' class='text-center'>載入中...</td></tr>";
    try {
        const dept = document.getElementById("sales-filter-dept").value;
        const cat = document.getElementById("sales-filter-cat").value;
        const sDate = document.getElementById("sales-filter-start").value;
        const eDate = document.getElementById("sales-filter-end").value;
        let url = '/sales?';
        if(dept) url += `department=${dept}&`;
        if(cat) url += `category=${cat}&`;
        if(sDate) url += `start_date=${sDate}T00:00:00Z&`;
        if(eDate) url += `end_date=${eDate}T23:59:59Z`;

        const result = await apiGet(url + (url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dateStr = new Date(d.date).toLocaleDateString();
            tbody.innerHTML += `
                <tr>
                    <td><input type="checkbox" class="row-checkbox" value="${d.order_id ?? ''}"></td>
                    <td>${dateStr}</td>
                    <td>${d.order_id ?? ''}</td>
                    <td><span class="badge badge-secondary">${d.category ?? ''}</span></td>
                    <td>${d.customer_name || d.customer_id || ''}</td>
                    <td>${d.plate_number || ''}</td>
                    <td>$${d.grand_total ?? ''}</td>
                    <td><span class="badge ${d.payment_status==='收現'?'badge-success':'badge-warning'}">${d.payment_status ?? ''}</span></td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="downloadSalesExcel('${d.order_id ?? ''}')" title="下載出貨單Excel"><i class="fas fa-file-excel"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("sales-pagination", total, page, 30, "loadSalesOrders(PAGE)");
    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan='9' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`;
    }
}

async function loadQuotes(page = 1) {
    const tbody = document.querySelector("#quotes-table tbody");
    try {
        const type = document.getElementById("quotes-filter-type").value;
        let url = '/quotes?';
        if(type) url += `quote_type=${type}`;
        
        const result = await apiGet(url + (url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dateStr = new Date(d.date).toLocaleDateString();
            tbody.innerHTML += `
                <tr>
                    <td><input type="checkbox" class="row-checkbox" value="${d.quote_id ?? ''}"></td>
                    <td>${dateStr}</td>
                    <td>${d.quote_id ?? ''}</td>
                    <td>${d.quote_type==='customer'?'客戶報價':'廠商報價'}</td>
                    <td>${d.party_name || d.party_id || ''}</td>
                    <td>$${d.grand_total ?? ''}</td>
                    <td>${d.valid_until ? new Date(d.valid_until).toLocaleDateString() : '-'}</td>
                    <td>${d.note || ''}</td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="downloadQuoteExcel('${d.quote_id ?? ''}')" title="下載報價單Excel"><i class="fas fa-file-excel"></i></button>
                        ${d.is_converted ? 
                          `<span class="text-success text-xs font-bold" style="margin-left: 8px; color: var(--success);"><i class="fas fa-check-circle"></i> 已轉換</span>` : 
                          `<button class="btn btn-sm btn-icon btn-primary" onclick="convertQuote('${d.quote_id ?? ''}', '${d.quote_type ?? ''}')" title="轉訂單"><i class="fas fa-exchange-alt"></i></button>`
                        }
                    </td>
                </tr>
            `;
        });
        renderPagination("quotes-pagination", total, page, 30, "loadQuotes(PAGE)");
    } catch (e) { console.error(e); }
}

async function convertQuote(quote_id, type) {
    if(!confirm(`確定將報價單 ${quote_id} 轉為${type==='customer'?'出貨單':'進貨單'}嗎？`)) return;
    const targetId = prompt("請輸入新單號 (留空將自動產生)");
    try {
        await apiPost(`/quotes/${quote_id}/convert`, {
            order_id: targetId || `SO-${quote_id}`,
            purchase_id: targetId || `PO-${quote_id}`
        });
        alert("轉換成功！");
        loadQuotes();
    } catch(e) { alert("轉換失敗: " + e.message); }
}

async function loadPurchases(page = 1) {
    const tbody = document.querySelector("#purchases-table tbody");
    if(!tbody) return;
    try {
        const result = await apiGet(`/purchases?page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dateStr = new Date(d.date).toLocaleDateString();
            tbody.innerHTML += `
                <tr>
                    <td><input type="checkbox" class="row-checkbox" value="${d.purchase_id ?? ''}"></td>
                    <td>${dateStr}</td>
                    <td>${d.purchase_id ?? ''}</td>
                    <td>${d.vendor_name || d.vendor_id || ''}</td>
                    <td>$${d.grand_total ?? ''}</td>
                    <td><span class="badge ${d.payment_status==='付現'?'badge-success':'badge-warning'}">${d.payment_status ?? ''}</span></td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="downloadPurchaseExcel('${d.purchase_id ?? ''}')" title="下載進貨單Excel"><i class="fas fa-file-excel"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("purchases-pagination", total, page, 30, "loadPurchases(PAGE)");
    } catch(e) { console.error(e); }
}

// ==================== Notes Module ====================
async function loadNotes(page = 1) {
    const tbody = document.querySelector("#notes-table tbody");
    if(!tbody) return;
    try {
        const type = document.getElementById("notes-filter-type").value;
        const status = document.getElementById("notes-filter-status").value;
        let url = '/notes?';
        if(type) url += `type=${type}&`;
        if(status) url += `status=${status}`;
        
        const result = await apiGet(url + (url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dueStr = new Date(d.due_date).toLocaleDateString();
            tbody.innerHTML += `
                <tr>
                    <td><span class="badge ${d.type==='receivable'?'badge-success':'badge-danger'}">${d.type==='receivable'?'應收':'應付'}</span></td>
                    <td>${d.note_number ?? ''}</td>
                    <td>${d.party_name || ''}</td>
                    <td>$${d.amount ?? ''}</td>
                    <td>${dueStr}</td>
                    <td><span class="badge ${d.status==='cleared'?'badge-secondary':'badge-warning'}">${d.status==='cleared'?'已兌現':'未兌現'}</span></td>
                    <td>
                        ${d.status === 'pending' ? `<button class="btn btn-sm btn-primary" onclick="clearNote('${d.note_id ?? ''}')">兌現</button>` : ''}
                        <button class="btn btn-sm btn-danger" onclick="deleteNote('${d.note_id ?? ''}')"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("notes-pagination", total, page, 30, "loadNotes(PAGE)");
    } catch(e) { console.error(e); }
}

async function openNoteModal() {
    document.getElementById("note-form").reset();
    document.getElementById("note-due-date").value = new Date().toISOString().split("T")[0];
    openModal("note-modal");
}

async function saveNote(e) {
    e.preventDefault();
    const payload = {
        note_id: `NT-${Date.now()}`,
        type: document.getElementById("note-type").value,
        note_number: document.getElementById("note-number").value,
        party_name: document.getElementById("note-party").value,
        amount: parseFloat(document.getElementById("note-amount").value) || 0,
        due_date: document.getElementById("note-due-date").value + "T00:00:00Z",
        note: document.getElementById("note-desc").value,
        status: "pending"
    };
    try {
        await apiPost("/notes", payload);
        closeModal("note-modal");
        loadNotes();
    } catch(err) { alert(err.message); }
}

async function clearNote(id) {
    if(!confirm("確定將此票據標示為已兌現？")) return;
    try { await apiPut(`/notes/${id}/clear`, {}); loadNotes(); } catch(e){ alert(e.message); }
}

async function deleteNote(id) {
    if(!confirm("刪除此票據？")) return;
    try { await apiDelete(`/notes/${id}`); loadNotes(); } catch(e){ alert(e.message); }
}

// ==================== System Logs ====================
async function loadLogs(page = 1) {
    const tbody = document.querySelector("#logs-table tbody");
    if(!tbody) return;
    try {
        const user = document.getElementById("logs-filter-user").value;
        let url = '/logs';
        if(user) url += `?username=${user}`;
        
        const result = await apiGet(url + (url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dateStr = new Date(d.timestamp).toLocaleString();
            tbody.innerHTML += `
                <tr>
                    <td>${dateStr}</td>
                    <td>${d.username ?? ''}</td>
                    <td><span class="badge badge-secondary">${d.action ?? ''}</span></td>
                    <td>${d.target ?? ''}</td>
                    <td>${d.details ?? ''}</td>
                </tr>
            `;
        });
        renderPagination("logs-pagination", total, page, 30, "loadLogs(PAGE)");
    } catch(e) { console.error(e); }
}

// ... Additional loaders for Inv, Pur, Cust, Ven mapped similarly ...
// Let's implement AR/AP loading:

// ==================== FINANCIAL MODULE LOADERS ====================

function switchArTab(tab) {
    document.getElementById("ar-summary-tab").classList.remove("active");
    document.getElementById("ar-detail-tab").classList.remove("active");
    document.querySelectorAll("#ar-section .tab").forEach(t => t.classList.remove("active"));
    
    if(tab === 'summary') {
        document.getElementById("ar-summary-tab").classList.add("active");
        document.querySelectorAll("#ar-section .tab")[0].classList.add("active");
        loadArSummary();
    } else {
        document.getElementById("ar-detail-tab").classList.add("active");
        document.querySelectorAll("#ar-section .tab")[1].classList.add("active");
        loadArDetails();
    }
}

async function loadArSummary(page = 1) {
    try {
        const result = await apiGet('/receivables/summary' + (typeof url !== 'undefined' && url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        const tbody = document.querySelector("#ar-summary-table tbody");
        tbody.innerHTML = "";
        let totalUnpaid = 0;
        data.forEach(d => {
            totalUnpaid += d.total_balance;
            tbody.innerHTML += `
                <tr>
                    <td>${d.customer_name || d._id || ''}</td>
                    <td>$${d.total_amount ?? ''}</td>
                    <td>$${d.total_paid ?? ''}</td>
                    <td style="color:var(--danger); font-weight:bold;">$${d.total_balance ?? ''}</td>
                    <td><button class="btn btn-sm btn-primary" onclick="openPaymentModal('receivable', '${d._id ?? ''}', '${d.customer_name ?? ''}', ${d.total_balance ?? ''})">沖帳</button></td>
                </tr>
            `;
        });
        
        // Update stat cards
        document.getElementById("ar-stat-cards").innerHTML = `
            <div class="stat-card">
                <div class="stat-icon danger"><i class="fas fa-hand-holding-usd"></i></div>
                <div class="stat-info"><h4>未收總餘額</h4><p>$${totalUnpaid}</p></div>
            </div>
            <div class="stat-card">
                <div class="stat-icon primary"><i class="fas fa-users"></i></div>
                <div class="stat-info"><h4>欠款客戶數</h4><p>${data.length ?? ''}</p></div>
            </div>
        `;
        renderPagination("ar-summary-pagination", total, page, 30, "loadArSummary(PAGE)");
    } catch(e) { console.error(e); }
}

async function loadArDetails(page = 1) {
    try {
        const status = document.getElementById("ar-detail-status").value;
        const result = await apiGet(`/receivables?status=${status}&page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        const tbody = document.querySelector("#ar-detail-table tbody");
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td>${new Date(d.date).toLocaleDateString()}</td>
                    <td>${d.order_id ?? ''}</td>
                    <td>${d.customer_name ?? ''}</td>
                    <td>${d.plate_number || ''}</td>
                    <td>$${d.amount ?? ''}</td>
                    <td>$${d.paid_amount ?? ''}</td>
                    <td style="color:var(--danger);">$${d.balance ?? ''}</td>
                    <td><span class="badge ${d.status==='paid'?'badge-success':'badge-warning'}">${d.status ?? ''}</span></td>
                </tr>
            `;
        });
        renderPagination("ar-details-pagination", total, page, 30, "loadArDetails(PAGE)");
    } catch(e) { console.error(e); }
}

// Payment Modal
function openPaymentModal(type, refId = '', partyName = '', balance = 0) {
    document.getElementById("payment-form").reset();
    document.getElementById("pay-type").value = type;
    document.getElementById("pay-ref-id").value = refId;
    document.getElementById("pay-party-name").value = partyName;
    document.getElementById("pay-balance").value = balance;
    
    document.getElementById("payment-modal-title").innerText = type === 'receivable' ? '收款沖帳' : '付款沖帳';
    openModal("payment-modal");
}

async function submitPayment() {
    const payload = {
        payment_id: "PAY-" + Date.now(),
        payment_type: document.getElementById("pay-type").value,
        ref_id: document.getElementById("pay-ref-id").value,
        date: new Date().toISOString(),
        amount: parseFloat(document.getElementById("pay-amount").value),
        method: document.getElementById("pay-method").value
    };
    try {
        await apiPost("/payments", payload);
        alert("沖帳成功");
        closeModal("payment-modal");
        if(payload.payment_type === 'receivable') loadArSummary();
    } catch(e) { alert("失敗: " + e.message); }
}

// ==================== Reports ====================
function initReports() {
    const sel = document.getElementById("report-year");
    sel.innerHTML = "";
    const currentYear = new Date().getFullYear();
    for(let i=currentYear; i>=2020; i--) {
        sel.innerHTML += `<option value="${i}">${i}</option>`;
    }
    
    const monthSel = document.getElementById("report-month");
    monthSel.innerHTML = "<option value=''>全年</option>";
    for(let i=1; i<=12; i++) {
        monthSel.innerHTML += `<option value="${i}">${i}月</option>`;
    }
    loadReports();
}

async function loadReports() {
    const y = document.getElementById("report-year").value;
    const m = document.getElementById("report-month").value;
    
    try {
        let url = `/reports/profit-loss?year=${y}`;
        if(m) url += `&month=${m}`;
        
        const pl = await apiGet(url);
        document.getElementById("rep-revenue").innerText = `$${pl.total_revenue ?? ''}`;
        document.getElementById("rep-cost").innerText = `$${pl.total_cost ?? ''}`;
        document.getElementById("rep-profit").innerText = `$${pl.gross_profit ?? ''}`;
        document.getElementById("rep-margin").innerText = `${pl.margin_percent ?? ''}%`;
        
        // ABC Analysis
        const custAbc = await apiGet(`/reports/customer-abc?year=${y}`);
        const cTbody = document.querySelector("#rep-customer-abc tbody");
        cTbody.innerHTML = "";
        custAbc.forEach(c => {
            const badgeClass = c.rating==='A' ? 'badge-success' : (c.rating==='B' ? 'badge-primary' : 'badge-secondary');
            cTbody.innerHTML += `<tr><td>${c.customer_name ?? ''}</td><td>$${c.total_amount ?? ''}</td><td><span class="badge ${badgeClass}">${c.rating ?? ''}級</span></td></tr>`;
        });
        
        const venAbc = await apiGet(`/reports/vendor-abc?year=${y}`);
        const vTbody = document.querySelector("#rep-vendor-abc tbody");
        vTbody.innerHTML = "";
        venAbc.forEach(v => {
            const badgeClass = v.rating==='A' ? 'badge-success' : (v.rating==='B' ? 'badge-primary' : 'badge-secondary');
            vTbody.innerHTML += `<tr><td>${v.vendor_name ?? ''}</td><td>$${v.total_amount ?? ''}</td><td><span class="badge ${badgeClass}">${v.rating ?? ''}級</span></td></tr>`;
        });
        
        document.getElementById("report-content").classList.remove("hidden");
    } catch(e) { console.error(e); }
}

// ==================== Announcement ====================
async function loadAnnouncements() {
    try {
        const data = await apiGet("/announcements");
        if(data.content) {
            document.getElementById("announcement-marquee").innerText = data.content;
        }
    } catch(e){}
}


// ==================== Excel Print Engine ====================
function downloadSalesExcel(orderId) {
    // We open the URL directly to trigger the browser download
    const url = `${API_BASE}/print/sales/${orderId}`;
    downloadFileWithAuth(url, `SalesOrder_${orderId}.xlsx`);
}

async function downloadEnvelopes(type) {
    const tableId = type === 'customer' ? 'customers-table' : 'vendors-table';
    const checked = Array.from(document.querySelectorAll(`#${tableId} .row-checkbox:checked`)).map(cb => cb.value);
    if(checked.length === 0) { alert("請先勾選客戶/廠商"); return; }
    
    try {
        const res = await fetch(`${API_BASE}/print/envelopes?is_return=false`, {
            method: 'POST', headers: authHeaders(), body: JSON.stringify(checked)
        });
        if(!res.ok) throw new Error("列印失敗");
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'Envelope.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
    } catch(e) { alert(e.message); }
}

async function downloadLabels(type) {
    const tableId = type === 'customer' ? 'customers-table' : 'vendors-table';
    const checked = Array.from(document.querySelectorAll(`#${tableId} .row-checkbox:checked`)).map(cb => cb.value);
    if(checked.length === 0) { alert("請先勾選客戶/廠商"); return; }
    
    try {
        const res = await fetch(`${API_BASE}/print/labels`, {
            method: 'POST', headers: authHeaders(), body: JSON.stringify(checked)
        });
        if(!res.ok) throw new Error("列印失敗");
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'AddressLabels.xlsx';
        document.body.appendChild(a); a.click(); a.remove();
    } catch(e) { alert(e.message); }
}

function downloadFileWithAuth(url, filename) {
    fetch(url, { headers: { "Authorization": `Bearer ${currentToken}` } })
        .then(response => response.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a); 
            a.click();    
            a.remove();
        })
        .catch(err => alert("下載失敗"));
}

// ==================== Payroll Module ====================
function switchPayrollTab(tab) {
    document.getElementById("pr-emp-tab").classList.remove("active");
    document.getElementById("pr-salary-tab").classList.remove("active");
    document.getElementById("pr-emp-content").classList.add("hidden");
    document.getElementById("pr-salary-content").classList.add("hidden");
    
    if(tab === 'emp') {
        document.getElementById("pr-emp-tab").classList.add("active");
        document.getElementById("pr-emp-content").classList.remove("hidden");
        loadEmployees();
    } else {
        document.getElementById("pr-salary-tab").classList.add("active");
        document.getElementById("pr-salary-content").classList.remove("hidden");
        loadPayroll();
    }
}

async function loadEmployees(page = 1) {
    try {
        const result = await apiGet(`/employees?page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        const tbody = document.querySelector("#emp-table tbody");
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td>${d.employee_id ?? ''}</td>
                    <td>${d.name ?? ''}</td>
                    <td>${new Date(d.hire_date).toLocaleDateString()}</td>
                    <td>$${d.base_salary ?? ''}</td>
                    <td><span class="badge ${d.status==='active'?'badge-success':'badge-secondary'}">${d.status ?? ''}</span></td>
                    <td><button class="btn btn-sm btn-danger" onclick="deleteEmployee('${d.employee_id ?? ''}')"><i class="fas fa-trash"></i></button></td>
                </tr>
            `;
        });
        renderPagination("employees-pagination", total, page, 30, "loadEmployees(PAGE)");
    } catch(e) { console.error(e); }
}

async function loadPayroll(page = 1) {
    try {
        const y = document.getElementById("pr-year").value;
        const m = document.getElementById("pr-month").value;
        const result = await apiGet(`/payroll?year=${y}&month=${m}&page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        const tbody = document.querySelector("#payroll-table tbody");
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td>${d.year ?? ''}-${d.month ?? ''}</td>
                    <td>${d.employee_name ?? ''}</td>
                    <td>$${d.base_salary ?? ''}</td>
                    <td style="color:var(--success)">+$${d.bonus ?? ''}</td>
                    <td style="color:var(--danger)">-$${d.deduction ?? ''}</td>
                    <td style="font-weight:bold;">$${d.net_pay ?? ''}</td>
                    <td><span class="badge ${d.status==='paid'?'badge-success':'badge-warning'}">${d.status ?? ''}</span></td>
                    <td>
                        ${d.status === 'unpaid' ? `<button class="btn btn-sm btn-primary" onclick="payPayroll('${d.payroll_id ?? ''}')">發薪</button>` : ''}
                        <button class="btn btn-sm btn-danger" onclick="deletePayroll('${d.payroll_id ?? ''}')"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `;
        });
    } catch(e) { console.error(e); }
}

async function payPayroll(id) {
    if(!confirm("確定已發放此薪資？")) return;
    try {
        await apiPut(`/payroll/${id}/pay`, {});
        loadPayroll();
    } catch(e) { alert("失敗: " + e.message); }
}


// === Extra Download Handlers ===
function downloadPurchaseExcel(orderId) { downloadFileWithAuth(`${API_BASE}/print/purchases/${orderId}`, `PurchaseOrder_${orderId}.xlsx`); }
function downloadQuoteExcel(quoteId) { downloadFileWithAuth(`${API_BASE}/print/quotes/${quoteId}`, `Quote_${quoteId}.xlsx`); }

// === Payroll Modals ===
let currentEmployees = [];

async function openEmployeeModal() {
    document.getElementById("employee-form").reset();
    document.getElementById("emp-id").value = `E${Date.now().toString().slice(-4)}`;
    document.getElementById("emp-date").value = new Date().toISOString().split("T")[0];
    openModal("employee-modal");
}

async function saveEmployee(e) {
    e.preventDefault();
    const payload = {
        employee_id: document.getElementById("emp-id").value,
        name: document.getElementById("emp-name").value,
        phone: document.getElementById("emp-phone").value,
        hire_date: document.getElementById("emp-date").value + "T00:00:00Z",
        base_salary: parseFloat(document.getElementById("emp-salary").value),
        status: document.getElementById("emp-status").value,
        role: "staff"
    };
    try {
        await apiPost("/employees", payload);
        closeModal("employee-modal");
        loadEmployees();
    } catch(err) { alert(err.message); }
}

async function deleteEmployee(id) {
    if(!confirm("刪除此員工？")) return;
    try { await apiDelete(`/employees/${id}`); loadEmployees(); } catch(e){ alert(e.message); }
}

async function openPayrollModal() {
    document.getElementById("payroll-form").reset();
    document.getElementById("pr-rec-year").value = new Date().getFullYear();
    document.getElementById("pr-rec-month").value = new Date().getMonth() + 1;
    
    // Load employee list into select
    const emps = await apiGet("/employees");
    currentEmployees = emps;
    const sel = document.getElementById("pr-rec-emp");
    sel.innerHTML = "<option value=''>請選擇員工</option>";
    emps.filter(e => e.status === 'active').forEach(e => {
        sel.innerHTML += `<option value="${e.employee_id ?? ''}">${e.name ?? ''}</option>`;
    });
    
    openModal("payroll-modal");
}

function populatePayrollBase() {
    const empId = document.getElementById("pr-rec-emp").value;
    const emp = currentEmployees.find(e => e.employee_id === empId);
    if(emp) {
        document.getElementById("pr-rec-base").value = emp.base_salary;
        calcNetPay();
    }
}

function calcNetPay() {
    const base = parseFloat(document.getElementById("pr-rec-base").value) || 0;
    const comm = parseFloat(document.getElementById("pr-rec-comm").value) || 0;
    const bonus = parseFloat(document.getElementById("pr-rec-bonus").value) || 0;
    const overtime = parseFloat(document.getElementById("pr-rec-overtime").value) || 0;
    const deduct = parseFloat(document.getElementById("pr-rec-deduct").value) || 0;
    
    const net = base + comm + bonus + overtime - deduct;
    document.getElementById("pr-rec-net").value = net;
}

async function savePayrollRecord(e) {
    e.preventDefault();
    const sel = document.getElementById("pr-rec-emp");
    const empName = sel.options[sel.selectedIndex].text;
    
    const payload = {
        payroll_id: `PR-${Date.now()}`,
        employee_id: document.getElementById("pr-rec-emp").value,
        employee_name: empName,
        year: parseInt(document.getElementById("pr-rec-year").value),
        month: parseInt(document.getElementById("pr-rec-month").value),
        base_salary: parseFloat(document.getElementById("pr-rec-base").value) || 0,
        commission: parseFloat(document.getElementById("pr-rec-comm").value) || 0,
        performance_bonus: parseFloat(document.getElementById("pr-rec-bonus").value) || 0,
        overtime_pay: parseFloat(document.getElementById("pr-rec-overtime").value) || 0,
        deduction: parseFloat(document.getElementById("pr-rec-deduct").value) || 0,
        net_pay: parseFloat(document.getElementById("pr-rec-net").value) || 0,
        note: document.getElementById("pr-rec-note").value
    };
    try {
        await apiPost("/payroll", payload);
        closeModal("payroll-modal");
        loadPayroll();
    } catch(err) { alert(err.message); }
}

async function deletePayroll(id) {
    if(!confirm("刪除此薪資單？")) return;
    try { await apiDelete(`/payroll/${id}`); loadPayroll(); } catch(e){ alert(e.message); }
}

// Global scope export for HTML onClick bindings
window.downloadSalesExcel = downloadSalesExcel;
window.downloadPurchaseExcel = downloadPurchaseExcel;
window.downloadQuoteExcel = downloadQuoteExcel;
window.downloadEnvelopes = downloadEnvelopes;
window.downloadLabels = downloadLabels;
window.switchPayrollTab = switchPayrollTab;
window.loadEmployees = loadEmployees;
window.loadPayroll = loadPayroll;
window.payPayroll = payPayroll;
window.openEmployeeModal = openEmployeeModal;
window.saveEmployee = saveEmployee;
window.deleteEmployee = deleteEmployee;
window.openPayrollModal = openPayrollModal;
window.populatePayrollBase = populatePayrollBase;
window.calcNetPay = calcNetPay;
window.savePayrollRecord = savePayrollRecord;
window.deletePayroll = deletePayroll;
window.loadSalesOrders = loadSalesOrders;
window.loadPurchases = loadPurchases;
window.loadQuotes = loadQuotes;
window.loadNotes = loadNotes;
window.openNoteModal = openNoteModal;
window.saveNote = saveNote;
window.clearNote = clearNote;
window.deleteNote = deleteNote;
window.loadLogs = loadLogs;
window.convertQuote = convertQuote;
window.switchArTab = switchArTab;
window.loadArDetails = loadArDetails;
window.openPaymentModal = openPaymentModal;
window.submitPayment = submitPayment;
window.initReports = initReports;
window.loadReports = loadReports;
window.openOrderModal = openOrderModal;
window.saveOrder = saveOrder;
window.closeModal = closeModal;
window.addLineItem = addLineItem;
window.removeLineItem = removeLineItem;
window.calcLineAmount = calcLineAmount;
window.openTireSelector = openTireSelector;
window.renderTireSvg = renderTireSvg;
window.toggleTire = toggleTire;
window.confirmTireSelection = confirmTireSelection;
window.lookupProduct = lookupProduct;
window.savePermissions = savePermissions;

// ==================== User Management ====================
async function loadUsers(page = 1) {
    const tbody = document.querySelector("#users-table tbody");
    tbody.innerHTML = "<tr><td colspan='5' class='text-center'>載入中...</td></tr>";
    try {
        const result = await apiGet(`/users?page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(u => {
            const dateStr = u.created_at ? new Date(u.created_at).toLocaleDateString() : '';
            const roleBadge = u.role === 'owner' ? 'badge-primary' : (u.role === 'manager' ? 'badge-warning' : 'badge-secondary');
            const statusBadge = u.is_active ? '<span class="badge badge-success">啟用</span>' : '<span class="badge badge-danger">停用</span>';
            tbody.innerHTML += `
                <tr>
                    <td>${u.username ?? ''}</td>
                    <td><span class="badge ${roleBadge}">${u.role ?? ''}</span></td>
                    <td>${statusBadge}</td>
                    <td>${dateStr}</td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="openUserPasswordModal('${u.username ?? ''}')" title="修改密碼"><i class="fas fa-key"></i></button>
                        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteUser('${u.username ?? ''}')" title="刪除帳號"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("users-pagination", total, page, 30, "loadUsers(PAGE)");
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan='5' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`;
    }
}

function openUserModal() {
    document.getElementById("u-username").value = "";
    document.getElementById("u-password").value = "";
    document.getElementById("u-role").value = "staff";
    document.getElementById("user-modal").classList.add("show");
}

async function saveUser() {
    const payload = {
        username: document.getElementById("u-username").value,
        password: document.getElementById("u-password").value,
        role: document.getElementById("u-role").value,
        is_active: true
    };
    try {
        const res = await fetch(`${API_BASE}/users`, {
            method: "POST", headers: authHeaders(), body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        closeModal("user-modal");
        loadUsers();
    } catch(e) { alert("建立失敗: " + e.message); }
}

function openUserPasswordModal(username) {
    document.getElementById("pw-username").value = username;
    document.getElementById("pw-username-display").innerText = username;
    document.getElementById("pw-new").value = "";
    document.getElementById("user-pw-modal").classList.add("show");
}

async function saveUserPassword() {
    const username = document.getElementById("pw-username").value;
    const payload = { password: document.getElementById("pw-new").value };
    try {
        const res = await fetch(`${API_BASE}/users/${username}/password`, {
            method: "PUT", headers: authHeaders(), body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        alert("密碼修改成功");
        closeModal("user-pw-modal");
    } catch(e) { alert("修改失敗: " + e.message); }
}

async function deleteUser(username) {
    if(!confirm(`確定要刪除帳號 ${username} 嗎？`)) return;
    try {
        const res = await fetch(`${API_BASE}/users/${username}`, {
            method: "DELETE", headers: authHeaders()
        });
        if(!res.ok) throw new Error(await res.text());
        loadUsers();
    } catch(e) { alert("刪除失敗: " + e.message); }
}

window.loadUsers = loadUsers;
window.openUserModal = openUserModal;
window.saveUser = saveUser;
window.openUserPasswordModal = openUserPasswordModal;
window.saveUserPassword = saveUserPassword;
window.deleteUser = deleteUser;

// ==================== RESTORED MISSING FUNCTIONS ====================

// --- Customers & Vendors ---
async function loadCustomers(page = 1) {
    const tbody = document.querySelector("#customers-table tbody");
    tbody.innerHTML = "<tr><td colspan='6' class='text-center'>載入中...</td></tr>";
    try {
        const result = await apiGet(`/customers?page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td><input type="checkbox" class="row-checkbox" value="${d.customer_id ?? ''}"></td>
                    <td>${d.customer_id ?? ''}</td>
                    <td>${d.name ?? ''}</td>
                    <td>${d.tax_id || ''}</td>
                    <td>${d.phone || ''}</td>
                    <td>${d.vehicles ? d.vehicles.length : 0}</td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="openPartyModal('customer', '${d.customer_id ?? ''}')" title="編輯"><i class="fas fa-edit"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("customers-pagination", total, page, 30, "loadCustomers(PAGE)");
    } catch(e) { tbody.innerHTML = `<tr><td colspan='6' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`; }
}

async function loadVendors(page = 1) {
    const tbody = document.querySelector("#vendors-table tbody");
    tbody.innerHTML = "<tr><td colspan='6' class='text-center'>載入中...</td></tr>";
    try {
        const result = await apiGet(`/vendors?page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td><input type="checkbox" class="row-checkbox" value="${d.vendor_id ?? ''}"></td>
                    <td>${d.vendor_id ?? ''}</td>
                    <td>${d.name ?? ''}</td>
                    <td>${d.tax_id || ''}</td>
                    <td>${d.phone || ''}</td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-secondary" onclick="openPartyModal('vendor', '${d.vendor_id ?? ''}')" title="編輯"><i class="fas fa-edit"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("vendors-pagination", total, page, 30, "loadVendors(PAGE)");
    } catch(e) { tbody.innerHTML = `<tr><td colspan='6' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`; }
}

function openVendorModal(id) {
    openPartyModal('vendor', id);
}

function openPartyModal(type, id) {
    document.getElementById('party-form').reset();
    document.getElementById('party-type').value = type;
    document.getElementById('party-id-old').value = id || '';
    if(id) {
        document.getElementById('party-id').value = id;
        document.getElementById('party-id').readOnly = true;
        // Fetch existing data
        const endpoint = type === 'customer' ? `/customers/${id}` : `/vendors/${id}`;
        apiGet(endpoint).then(data => {
            if(data) {
                document.getElementById('party-name').value = data.name || '';
                document.getElementById('party-phone').value = data.phone || '';
                document.getElementById('party-address').value = data.address || '';
                document.getElementById('party-uniform').value = data.uniform_number || '';
            }
        });
    } else {
        document.getElementById('party-id').readOnly = false;
    }
    openModal('party-modal');
}

async function saveParty() {
    const type = document.getElementById('party-type').value;
    const oldId = document.getElementById('party-id-old').value;
    
    const payload = {
        name: document.getElementById('party-name').value,
        phone: document.getElementById('party-phone').value,
        address: document.getElementById('party-address').value,
        uniform_number: document.getElementById('party-uniform').value
    };
    
    const idField = type === 'customer' ? 'customer_id' : 'vendor_id';
    payload[idField] = document.getElementById('party-id').value;
    
    const method = oldId ? 'PUT' : 'POST';
    const url = oldId ? `/${type}s/${oldId}` : `/${type}s`;
    
    try {
        const res = await fetch(`${API_BASE}${url}`, { method, headers: authHeaders(), body: JSON.stringify(payload) });
        if(!res.ok) throw new Error(await res.text());
        closeModal('party-modal');
        if(type === 'customer') loadCustomers();
        else loadVendors();
    } catch(e) { alert("儲存失敗: " + e.message); }
}

// --- Inventory ---
function switchInvTab(tab) {
    document.querySelectorAll('#inventory-section .tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    loadInventory(tab);
}

let currentInvCategory = '';
let currentInvPage = 1;

async function loadInventory(category = '', page = 1) {
    currentInvCategory = category;
    currentInvPage = page;
    const tbody = document.querySelector("#inventory-table tbody");
    const isSedan = category === '轎車胎';
    const totalCols = isSedan ? 8 : 6;
    tbody.innerHTML = `<tr><td colspan='${totalCols}' class='text-center'>載入中...</td></tr>`;
    let url = `/products?page=${page}&limit=20`;
    if(category) url += `&category=${encodeURIComponent(category)}`;
    try {
        const result = await apiGet(url);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        
        // Toggle sedan columns visibility in header
        const sedanCols = document.querySelectorAll(".sedan-col");
        if (isSedan) {
            sedanCols.forEach(el => el.classList.remove('hidden'));
        } else {
            sedanCols.forEach(el => el.classList.add('hidden'));
        }
        
        if (!data || data.length === 0) {
            tbody.innerHTML = `<tr><td colspan='${totalCols}' class='text-center'>查無商品資料</td></tr>`;
        } else {
            data.forEach(d => {
                const pCode = d.product_code ?? '';
                const brand = d.brand ?? '';
                const spec = d.spec ?? '';
                const pattern = d.pattern ?? '';
                const extra1 = d.extra_field_1 ?? '';
                const extra2 = d.extra_field_2 ?? '';
                const stock = d.stock_qty ?? 0;
                tbody.innerHTML += `
                    <tr>
                        <td>${pCode}</td>
                        <td>${brand}</td>
                        <td>${spec}</td>
                        <td>${pattern}</td>
                        <td class="sedan-col ${isSedan ? '' : 'hidden'}">${extra1}</td>
                        <td class="sedan-col ${isSedan ? '' : 'hidden'}">${extra2}</td>
                        <td><strong>${stock}</strong></td>
                        <td>
                            <button class="btn btn-sm btn-primary" onclick="openStockAdjustModal('${pCode}', ${stock})">調整庫存</button>
                        </td>
                    </tr>
                `;
            });
        }
        renderInvPagination(total, page, 20);
    } catch(e) { tbody.innerHTML = `<tr><td colspan='${totalCols}' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`; }
}

function openStockAdjustModal(productCode, currentQty) {
    document.getElementById("adjust-product-code").value = productCode ?? '';
    document.getElementById("adjust-current-qty").value = currentQty ?? 0;
    document.getElementById("adjust-qty").value = "";
    document.getElementById("adjust-reason").value = "";
    openModal("stock-adjust-modal");
}

async function submitStockAdjustment() {
    const productCode = document.getElementById("adjust-product-code").value;
    const adjustment = parseInt(document.getElementById("adjust-qty").value);
    const reason = document.getElementById("adjust-reason").value;
    
    if (isNaN(adjustment)) {
        alert("請輸入有效的數量");
        return;
    }
    if (!reason.trim()) {
        alert("請輸入調整原因");
        return;
    }
    
    try {
        const response = await apiPost(`/products/${encodeURIComponent(productCode)}/adjust_stock`, {
            adjustment: adjustment,
            reason: reason
        });
        alert("庫存調整成功");
        closeModal("stock-adjust-modal");
        loadInventory(currentInvCategory, currentInvPage);
    } catch (e) {
        alert("庫存調整失敗: " + (e.message || e));
    }
}


function renderInvPagination(total, currentPage, limit) {
    let container = document.getElementById("inventory-pagination");
    if (!container) {
        container = document.createElement("div");
        container.id = "inventory-pagination";
        container.className = "pagination-controls mt-4 flex justify-center gap-2";
        document.getElementById("inventory-table").parentElement.appendChild(container);
    }
    const totalPages = Math.ceil(total / limit) || 1;
    let html = '';
    
    html += `<button class="btn btn-sm ${currentPage <= 1 ? 'btn-secondary' : 'btn-primary'}" ${currentPage <= 1 ? 'disabled' : ''} onclick="loadInventory('${currentInvCategory}', ${currentPage - 1})">上一頁</button>`;
    html += `<span class="px-3 py-1">第 ${currentPage} 頁 / 共 ${totalPages} 頁 (總共 ${total} 筆)</span>`;
    html += `<button class="btn btn-sm ${currentPage >= totalPages ? 'btn-secondary' : 'btn-primary'}" ${currentPage >= totalPages ? 'disabled' : ''} onclick="loadInventory('${currentInvCategory}', ${currentPage + 1})">下一頁</button>`;
    
    container.innerHTML = html;
}


function printInventory() {
    window.print();
}

// --- AP (應付帳款) ---
function switchApTab(tab) {
    document.getElementById("ap-summary-tab").classList.remove("active");
    document.getElementById("ap-detail-tab").classList.remove("active");
    document.querySelectorAll("#ap-section .tab").forEach(t => t.classList.remove("active"));
    
    if(tab === 'summary') {
        document.getElementById("ap-summary-tab").classList.add("active");
        document.querySelectorAll("#ap-section .tab")[0].classList.add("active");
        loadApSummary();
    } else {
        document.getElementById("ap-detail-tab").classList.add("active");
        document.querySelectorAll("#ap-section .tab")[1].classList.add("active");
        loadApDetails();
    }
}

async function loadApSummary(page = 1) {
    const tbody = document.querySelector("#ap-summary-table tbody");
    tbody.innerHTML = "<tr><td colspan='5' class='text-center'>載入中...</td></tr>";
    try {
        const result = await apiGet("/payables/summary" + (typeof url !== 'undefined' && url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            tbody.innerHTML += `
                <tr>
                    <td>${d.vendor_name || d.vendor_id || ''}</td>
                    <td>$${d.total_payable ?? ''}</td>
                    <td>$${d.total_paid ?? ''}</td>
                    <td class="text-danger"><strong>$${d.balance ?? ''}</strong></td>
                    <td>
                        <button class="btn btn-sm btn-icon btn-primary" onclick="openPaymentModal('payable', '${d.vendor_id ?? ''}')" title="付款沖帳"><i class="fas fa-money-bill-wave"></i></button>
                    </td>
                </tr>
            `;
        });
        renderPagination("ap-summary-pagination", total, page, 30, "loadApSummary(PAGE)");
    } catch(e) { tbody.innerHTML = `<tr><td colspan='5' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`; }
}

async function loadApDetails(page = 1) {
    const tbody = document.querySelector("#ap-detail-table tbody");
    tbody.innerHTML = "<tr><td colspan='8' class='text-center'>載入中...</td></tr>";
    try {
        const result = await apiGet("/payables" + (typeof url !== 'undefined' && url.includes('?') ? '&' : '?') + `page=${page}&limit=30`);
        const data = result.data;
        const total = result.total;
        tbody.innerHTML = "";
        data.forEach(d => {
            const dateStr = new Date(d.date).toLocaleDateString();
            const statusBadge = d.status === 'paid' ? '<span class="badge badge-success">已結清</span>' : 
                                (d.status === 'partial' ? '<span class="badge badge-warning">部分付款</span>' : '<span class="badge badge-danger">未付款</span>');
            tbody.innerHTML += `
                <tr>
                    <td>${dateStr}</td>
                    <td>${d.purchase_id ?? ''}</td>
                    <td>${d.vendor_name || d.vendor_id || ''}</td>
                    <td>${d.invoice_number || ''}</td>
                    <td>$${d.amount ?? ''}</td>
                    <td>$${d.paid_amount ?? ''}</td>
                    <td><strong class="text-danger">$${d.amount - d.paid_amount}</strong></td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        });
        renderPagination("ap-details-pagination", total, page, 30, "loadApDetails(PAGE)");
    } catch(e) { tbody.innerHTML = `<tr><td colspan='8' class='text-center text-danger'>載入失敗: ${e.message ?? ''}</td></tr>`; }
}

// --- Utils ---
function batchPrint(type) {
    if(type === 'sales') {
        const checked = Array.from(document.querySelectorAll("#sales-table .row-checkbox:checked")).map(cb => cb.value);
        if(checked.length === 0) { alert("請先勾選單據"); return; }
        checked.forEach(id => downloadSalesExcel(id));
    }
    else if(type === 'quote') {
        const checked = Array.from(document.querySelectorAll("#quotes-table .row-checkbox:checked")).map(cb => cb.value);
        if(checked.length === 0) { alert("請先勾選單據"); return; }
        checked.forEach(id => downloadQuoteExcel(id));
    }
    else if(type === 'purchase') {
        const checked = Array.from(document.querySelectorAll("#purchases-table .row-checkbox:checked")).map(cb => cb.value);
        if(checked.length === 0) { alert("請先勾選單據"); return; }
        checked.forEach(id => downloadPurchaseExcel(id));
    }
}

function openAnnouncementModal() {
    const currentText = document.getElementById("announcement-marquee").innerText;
    document.getElementById("announcement-text").value = currentText;
    openModal('announcement-modal');
}

async function saveAnnouncement() {
    const text = document.getElementById("announcement-text").value;
    try {
        const res = await fetch(`${API_BASE}/announcements`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ content: text })
        });
        if(!res.ok) throw new Error(await res.text());
        closeModal('announcement-modal');
        loadAnnouncements();
    } catch(e) {
        alert("公告更新失敗: " + e.message);
    }
}

function closePrintPreview() {
    closeModal('print-modal');
}

function executePrint() {
    window.print();
}

function printMailingLabels(type) {
    downloadLabels(type);
}

// Expose to window
window.loadCustomers = loadCustomers;
window.loadVendors = loadVendors;
window.openVendorModal = openVendorModal;
window.openPartyModal = openPartyModal;
window.saveParty = saveParty;
window.switchInvTab = switchInvTab;
window.loadInventory = loadInventory;
window.printInventory = printInventory;
window.switchApTab = switchApTab;
window.loadApSummary = loadApSummary;
window.loadApDetails = loadApDetails;
window.batchPrint = batchPrint;
window.openAnnouncementModal = openAnnouncementModal;
window.closePrintPreview = closePrintPreview;
window.executePrint = executePrint;
window.printMailingLabels = printMailingLabels;
window.saveAnnouncement = saveAnnouncement;
window.closePrintPreview = closePrintPreview;
window.openStockAdjustModal = openStockAdjustModal;
window.submitStockAdjustment = submitStockAdjustment;
window.lookupProduct = lookupProduct;


function renderPagination(containerId, total, currentPage, limit, loadFnStr) {
    let container = document.getElementById(containerId);
    if (!container) {
        container = document.createElement("div");
        container.id = containerId;
        container.className = "pagination-controls mt-4 flex justify-center gap-2";
        const table = document.querySelector(`#${containerId.replace('-pagination', '-table')}`);
        if(table) table.parentElement.appendChild(container);
    }
    const totalPages = Math.ceil(total / limit) || 1;
    let html = '';
    html += `<button class="btn btn-sm ${currentPage <= 1 ? 'btn-secondary' : 'btn-primary'}" ${currentPage <= 1 ? 'disabled' : ''} onclick="${loadFnStr.replace('PAGE', String(currentPage - 1))}">上一頁</button>`;
    html += `<span class="px-3 py-1">第 ${currentPage} 頁 / 共 ${totalPages} 頁 (總共 ${total} 筆)</span>`;
    html += `<button class="btn btn-sm ${currentPage >= totalPages ? 'btn-secondary' : 'btn-primary'}" ${currentPage >= totalPages ? 'disabled' : ''} onclick="${loadFnStr.replace('PAGE', String(currentPage + 1))}">下一頁</button>`;
    if(container) container.innerHTML = html;
}
