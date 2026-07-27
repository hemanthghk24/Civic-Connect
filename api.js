const API_BASE_URL = "http://localhost:5000/api";

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.message || "Request failed.");
    }

    return data;
}

function saveUserSession(user) {
    localStorage.removeItem("civicconnectAdminLoggedIn");
    localStorage.removeItem("civicconnectAdmin");
    localStorage.setItem("civicconnectLoggedIn", "true");
    localStorage.setItem("civicconnectUser", JSON.stringify(user));
}

function getStoredUser() {
    const raw = localStorage.getItem("civicconnectUser");
    if (!raw) {
        return null;
    }

    try {
        return JSON.parse(raw);
    } catch (error) {
        return null;
    }
}

function clearUserSession() {
    localStorage.removeItem("civicconnectLoggedIn");
    localStorage.removeItem("civicconnectUser");
    localStorage.removeItem("lastComplaintCode");
}

function registerUser(payload) {
    return apiRequest("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}

function loginUser(payload) {
    return apiRequest("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}

function submitComplaint(formData) {
    return apiRequest("/complaints", {
        method: "POST",
        body: formData,
    });
}

function fetchComplaint(complaintCode) {
    return apiRequest(`/complaints/${encodeURIComponent(complaintCode)}`);
}

function fetchAnalytics() {
    return apiRequest("/analytics");
}

function fetchUserProfile(userId) {
    return apiRequest(`/users/${userId}`);
}

function fetchUserComplaints(userId) {
    return apiRequest(`/users/${userId}/complaints`);
}

function adminLogin(payload) {
    return apiRequest("/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}

function fetchAdminDashboard() {
    return apiRequest("/admin/dashboard");
}

function fetchAdminComplaints() {
    return apiRequest("/admin/complaints");
}

function fetchAdminUsers() {
    return apiRequest("/admin/users");
}

function updateAdminComplaint(complaintCode, payload) {
    return apiRequest(`/admin/complaints/${encodeURIComponent(complaintCode)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
}
