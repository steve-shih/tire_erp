const API_BASE = "http://localhost:8000/api";

// State management
let state = {
    token: localStorage.getItem("token") || null,
    user: null,
    customers: [],
    products: [],
    sales: []
};

// --- Initial Setup & Routing ---
document.addEventListener("DOMContentLoaded", () => {
    initApp();
    setupTime();
});

function setupTime() {
    const updateTime = () => {
        const now = new Date();
        document.getElementById("current-time-str").textContent = now.toLocaleTimeString("zh-TW", { hour: '2-digit', minute: '2-digit' });
    };
    updateTime();
    setInterval(updateTime, 60000);
}

function initApp() {
    if (state.token) {
        verifyTokenAndLoad();
    } else {
        showLoginScreen();
    }

    // Setup menu navigation listeners
    document.querySelectorAll(".menu-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            document.querySelectorAll(".menu-item").forEach(i => i.classList.remove("active"));
            item.classList.add("active");
            
            const target = item.getAttribute("data-target");
            switchSection(target);
        });
    });

    // Login Form Submission
    document.getElementById("login-form").addEventListener("submit", handleLogin);

    // Logout Action
    document.getElementById("logout-btn").addEventListener("click", handleLogout);

    // Search bar filters
    document.getElementById("customer-search").addEventListener("input", filterCustomers);
    document.getElementById("product-search").addEventListener("input", filterProducts);
    document.getElementById("sales-search").addEventListener("input", filterSales);

    // Schema form submissions
    document.getElementById("customer-form").addEventListener("submit", submitCustomer);
    document.getElementById("product-form").addEventListener("submit", submitProduct);
    document.getElementById("sales-form").addEventListener("submit", submitSalesOrder);
}

function switchSection(sectionId) {
    document.querySelectorAll(".content-section").forEach(s => s.classList.add("hidden"));
    document.getElementById(sectionId).classList.remove("hidden");
    
    // Set navbar section title
    const titles = {
        "dashboard-section": "儀表板首頁",
        "customers-section": "客戶管理",
        "products-section": "輪胎與產品庫存",
        "sales-section": "出貨與銷售紀錄"
    };
    document.getElementById("section-title").textContent = titles[sectionId] || "Tire ERP";

    // Reload active section data
    if (sectionId === "customers-section") loadCustomers();
    if (sectionId === "products-section") loadProducts();
    if (sectionId === "sales-section") loadSales();
    if (sectionId === "dashboard-section") loadDashboardStats();
}

// --- Authentication Operations ---
async function verifyTokenAndLoad() {
    try {
        const res = await fetch(`${API_BASE}/me`, {
            headers: { "Authorization": `Bearer ${state.token}` }
        });
        if (!res.ok) throw new Error("Invalid token");
        
        state.user = await res.json();
        showAppScreen();
        loadDashboardStats();
    } catch (e) {
        console.error(e);
        handleLogout();
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const usernameInput = document.getElementById("username").value;
    const passwordInput = document.getElementById("password").value;
    
    const errorAlert = document.getElementById("login-error");
    errorAlert.classList.add("hidden");

    try {
        const res = await fetch(`${API_BASE}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: usernameInput, password: passwordInput })
        });
        
        if (!res.ok) {
            throw new Error("Invalid login");
        }
        
        const data = await res.json();
        state.token = data.access_token;
        localStorage.setItem("token", state.token);
        
        // Auto-fetch profile
        await verifyTokenAndLoad();
    } catch (err) {
        errorAlert.classList.remove("hidden");
    }
}

function handleLogout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem("token");
    showLoginScreen();
}

function showLoginScreen() {
    document.getElementById("login-container").classList.remove("hidden");
    document.getElementById("app-container").classList.add("hidden");
}

function showAppScreen() {
    document.getElementById("login-container").classList.add("hidden");
    document.getElementById("app-container").classList.remove("hidden");
    
    // Update profile info on UI
    document.getElementById("user-display-name").textContent = state.user.username;
    document.getElementById("user-display-role").textContent = state.user.role.toUpperCase();
}

// --- API Helpers ---
async function apiRequest(endpoint, options = {}) {
    if (!state.token) return null;
    
    const url = `${API_BASE}${endpoint}`;
    options.headers = {
        ...options.headers,
        "Authorization": `Bearer ${state.token}`
    };
    
    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            handleLogout();
            return null;
        }
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Request failed");
        }
        return res.status !== 204 ? await res.json() : null;
    } catch (e) {
        alert(`錯誤: ${e.message}`);
        throw e;
    }
}

// --- Dashboard Stats ---
async function loadDashboardStats() {
    try {
        const customers = await apiRequest("/customers");
        const products = await apiRequest("/products");
        const sales = await apiRequest("/sales");
        
        if (customers) document.getElementById("stat-customers-count").textContent = customers.length;
        if (products) document.getElementById("stat-products-count").textContent = products.length;
        if (sales) document.getElementById("stat-sales-count").textContent = sales.length;
    } catch (e) {
        console.error("Failed to load statistics", e);
    }
}

// --- Customers Logic ---
async function loadCustomers() {
    const tableBody = document.getElementById("customers-table-body");
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> 載入中...</td></tr>`;
    
    const data = await apiRequest("/customers");
    if (!data) return;
    
    state.customers = data;
    renderCustomers(state.customers);
}

function renderCustomers(list) {
    const tableBody = document.getElementById("customers-table-body");
    tableBody.innerHTML = "";
    
    if (list.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center;">沒有符合的客戶資料</td></tr>`;
        return;
    }
    
    list.forEach(c => {
        const plates = c.vehicles.map(v => `<span class="badge badge-blue">${v.plate_number}</span>`).join(" ") || "無";
        const lastModified = c.updated_at ? new Date(c.updated_at).toLocaleString("zh-TW") : new Date(c.created_at).toLocaleString("zh-TW");
        const operator = c.updated_by || c.created_by || "未知";
        
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${c.customer_id}</strong></td>
            <td>${c.name}</td>
            <td>${c.phone || "—"}</td>
            <td>${c.address || "—"}</td>
            <td>${plates}</td>
            <td><i class="fa-solid fa-user-pen"></i> ${operator}</td>
            <td>${lastModified}</td>
            <td>
                <button class="btn btn-outline" style="padding: 5px 10px;" onclick="editCustomer('${c.customer_id}')">編輯</button>
                <button class="btn btn-outline-danger" style="padding: 5px 10px;" onclick="softDeleteCustomer('${c.customer_id}')">刪除</button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

function filterCustomers() {
    const query = document.getElementById("customer-search").value.toLowerCase();
    const filtered = state.customers.filter(c => 
        c.customer_id.toLowerCase().includes(query) ||
        c.name.toLowerCase().includes(query) ||
        (c.phone && c.phone.toLowerCase().includes(query)) ||
        (c.address && c.address.toLowerCase().includes(query))
    );
    renderCustomers(filtered);
}

// --- Products Logic ---
async function loadProducts() {
    const tableBody = document.getElementById("products-table-body");
    tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> 載入中...</td></tr>`;
    
    const data = await apiRequest("/products");
    if (!data) return;
    
    state.products = data;
    renderProducts(state.products);
}

function renderProducts(list) {
    const tableBody = document.getElementById("products-table-body");
    tableBody.innerHTML = "";
    
    if (list.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center;">沒有符合的產品庫存</td></tr>`;
        return;
    }
    
    list.forEach(p => {
        const lastModified = p.updated_at ? new Date(p.updated_at).toLocaleString("zh-TW") : new Date(p.created_at).toLocaleString("zh-TW");
        const operator = p.updated_by || p.created_by || "未知";
        const badgeClass = p.category === "卡車胎" ? "badge-orange" : p.category === "轎車胎" ? "badge-blue" : "badge-green";
        
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><code>${p.product_code}</code></td>
            <td>${p.brand}</td>
            <td>${p.spec}</td>
            <td>${p.pattern}</td>
            <td><span class="badge ${badgeClass}">${p.category}</span></td>
            <td><strong>${p.stock_qty}</strong></td>
            <td><i class="fa-solid fa-user-pen"></i> ${operator}</td>
            <td>${lastModified}</td>
            <td>
                <button class="btn btn-outline" style="padding: 5px 10px;" onclick="editProduct('${p.product_code}')">編輯</button>
                <button class="btn btn-outline-danger" style="padding: 5px 10px;" onclick="softDeleteProduct('${p.product_code}')">刪除</button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

function filterProducts() {
    const query = document.getElementById("product-search").value.toLowerCase();
    const filtered = state.products.filter(p => 
        p.product_code.toLowerCase().includes(query) ||
        p.brand.toLowerCase().includes(query) ||
        p.spec.toLowerCase().includes(query) ||
        p.pattern.toLowerCase().includes(query)
    );
    renderProducts(filtered);
}

// --- Sales Logic ---
async function loadSales() {
    const tableBody = document.getElementById("sales-table-body");
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> 載入中...</td></tr>`;
    
    const data = await apiRequest("/sales");
    if (!data) return;
    
    state.sales = data;
    renderSales(state.sales);
}

function renderSales(list) {
    const tableBody = document.getElementById("sales-table-body");
    tableBody.innerHTML = "";
    
    if (list.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center;">沒有符合的出貨單紀錄</td></tr>`;
        return;
    }
    
    list.forEach(s => {
        const orderDate = new Date(s.date).toLocaleString("zh-TW");
        const deptLabel = s.department === "truck" ? "卡車部" : "轎車部";
        
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${s.order_id}</strong></td>
            <td><span class="badge ${s.department === "truck" ? "badge-orange" : "badge-blue"}">${deptLabel}</span></td>
            <td>${orderDate}</td>
            <td>${s.customer_id}</td>
            <td><span class="badge badge-blue">${s.plate_number || "無"}</span></td>
            <td>$${s.grand_total.toLocaleString()}</td>
            <td><i class="fa-solid fa-user"></i> ${s.created_by}</td>
            <td>
                <button class="btn btn-outline-danger" style="padding: 5px 10px;" onclick="softDeleteSales('${s.order_id}')">撤銷</button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

function filterSales() {
    const query = document.getElementById("sales-search").value.toLowerCase();
    const filtered = state.sales.filter(s => 
        s.order_id.toLowerCase().includes(query) ||
        s.customer_id.toLowerCase().includes(query)
    );
    renderSales(filtered);
}

// --- CRUD Actions (Create / Edit / Soft Delete) ---

// Modal helpers
window.openCustomerModal = () => {
    document.getElementById("customer-form").reset();
    document.getElementById("c_id").disabled = false;
    document.getElementById("customer-modal-title").textContent = "新增客戶資料";
    document.getElementById("customer-modal").classList.remove("hidden");
};
window.closeCustomerModal = () => document.getElementById("customer-modal").classList.add("hidden");

window.openProductModal = () => {
    document.getElementById("product-form").reset();
    document.getElementById("p_code").disabled = false;
    document.getElementById("product-modal-title").textContent = "新增產品資料";
    document.getElementById("product-modal").classList.remove("hidden");
};
window.closeProductModal = () => document.getElementById("product-modal").classList.add("hidden");

window.openSalesModal = () => {
    document.getElementById("sales-form").reset();
    // Auto-generate random order_id
    document.getElementById("s_order_id").value = "TX" + Date.now().toString().slice(-6);
    document.getElementById("sales-modal").classList.remove("hidden");
};
window.closeSalesModal = () => document.getElementById("sales-modal").classList.add("hidden");

// Customer Form Submission
async function submitCustomer(e) {
    e.preventDefault();
    const customer_id = document.getElementById("c_id").value;
    const isEdit = document.getElementById("c_id").disabled;
    
    const vehiclesInput = document.getElementById("c_vehicle").value.trim();
    const vehicles = vehiclesInput ? [{ plate_number: vehiclesInput }] : [];
    
    const payload = {
        customer_id: customer_id,
        name: document.getElementById("c_name").value,
        phone: document.getElementById("c_phone").value,
        uniform_number: document.getElementById("c_uniform").value,
        address: document.getElementById("c_address").value,
        vehicles: vehicles
    };
    
    const url = isEdit ? `/customers/${customer_id}` : "/customers";
    const method = isEdit ? "PUT" : "POST";
    
    const res = await apiRequest(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    
    if (res) {
        closeCustomerModal();
        loadCustomers();
    }
}

window.editCustomer = (id) => {
    const cust = state.customers.find(c => c.customer_id === id);
    if (!cust) return;
    
    document.getElementById("c_id").value = cust.customer_id;
    document.getElementById("c_id").disabled = true;
    document.getElementById("c_name").value = cust.name;
    document.getElementById("c_phone").value = cust.phone || "";
    document.getElementById("c_uniform").value = cust.uniform_number || "";
    document.getElementById("c_address").value = cust.address || "";
    document.getElementById("c_vehicle").value = cust.vehicles[0]?.plate_number || "";
    
    document.getElementById("customer-modal-title").textContent = "修改客戶資料";
    document.getElementById("customer-modal").classList.remove("hidden");
};

window.softDeleteCustomer = async (id) => {
    if (!confirm(`確定要將客戶 ${id} 移至垃圾桶 (進行虛擬刪除) 嗎？`)) return;
    const res = await apiRequest(`/customers/${id}`, { method: "DELETE" });
    if (res) loadCustomers();
};

// Product Form Submission
async function submitProduct(e) {
    e.preventDefault();
    const product_code = document.getElementById("p_code").value;
    const isEdit = document.getElementById("p_code").disabled;
    
    const payload = {
        product_code: product_code,
        brand: document.getElementById("p_brand").value,
        spec: document.getElementById("p_spec").value,
        pattern: document.getElementById("p_pattern").value,
        category: document.getElementById("p_category").value,
        stock_qty: parseInt(document.getElementById("p_stock").value),
        price: parseFloat(document.getElementById("p_price").value)
    };
    
    const url = isEdit ? `/products/${product_code}` : "/products";
    const method = isEdit ? "PUT" : "POST";
    
    const res = await apiRequest(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    
    if (res) {
        closeProductModal();
        loadProducts();
    }
}

window.editProduct = (code) => {
    const prod = state.products.find(p => p.product_code === code);
    if (!prod) return;
    
    document.getElementById("p_code").value = prod.product_code;
    document.getElementById("p_code").disabled = true;
    document.getElementById("p_brand").value = prod.brand;
    document.getElementById("p_spec").value = prod.spec;
    document.getElementById("p_pattern").value = prod.pattern;
    document.getElementById("p_category").value = prod.category;
    document.getElementById("p_stock").value = prod.stock_qty;
    document.getElementById("p_price").value = prod.price;
    
    document.getElementById("product-modal-title").textContent = "修改產品資料";
    document.getElementById("product-modal").classList.remove("hidden");
};

window.softDeleteProduct = async (code) => {
    if (!confirm(`確定要將產品代碼 ${code} 移至垃圾桶 (進行虛擬刪除) 嗎？`)) return;
    const res = await apiRequest(`/products/${code}`, { method: "DELETE" });
    if (res) loadProducts();
};

// Sales Order Form Submission
async function submitSalesOrder(e) {
    e.preventDefault();
    const qty = parseInt(document.getElementById("s_qty").value);
    const price = parseFloat(document.getElementById("s_price").value);
    const amount = qty * price;
    
    const payload = {
        order_id: document.getElementById("s_order_id").value,
        department: document.getElementById("s_dept").value,
        date: new Date().toISOString(),
        customer_id: document.getElementById("s_cust_id").value,
        plate_number: document.getElementById("s_plate").value || null,
        items: [{
            product_code: document.getElementById("s_prod_code").value,
            qty: qty,
            price: price,
            amount: amount
        }],
        total_amount: amount,
        tax_amount: 0.0,
        grand_total: amount,
        payment_status: "cash"
    };
    
    const res = await apiRequest("/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    
    if (res) {
        closeSalesModal();
        loadSales();
    }
}

window.softDeleteSales = async (id) => {
    if (!confirm(`確定要撤銷出貨單 ${id} (這會恢復庫存數量) 嗎？`)) return;
    const res = await apiRequest(`/sales/${id}`, { method: "DELETE" });
    if (res) loadSales();
};
