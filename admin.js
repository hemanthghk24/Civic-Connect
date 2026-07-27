const ADMIN_PAGES = {
    dashboard: "admin_dashboard.html",
    complaints: "admin_complaints.html",
    analytics: "analytics_dashboard.html",
    users: "admin_users.html",
    profile: "admin_profile.html",
    login: "admin_login.html",
};

function isAdminLoggedIn() {
    return localStorage.getItem("civicconnectAdminLoggedIn") === "true";
}

function saveAdminSession(admin) {
    clearUserSession();
    localStorage.setItem("civicconnectAdminLoggedIn", "true");
    localStorage.setItem("civicconnectAdmin", JSON.stringify(admin));
}

function getStoredAdmin() {
    const raw = localStorage.getItem("civicconnectAdmin");
    if (!raw) {
        return null;
    }

    try {
        return JSON.parse(raw);
    } catch (error) {
        return null;
    }
}

function clearAdminSession() {
    localStorage.removeItem("civicconnectAdminLoggedIn");
    localStorage.removeItem("civicconnectAdmin");
}

function requireAdmin() {
    if (!isAdminLoggedIn()) {
        window.location.href = ADMIN_PAGES.login;
        return false;
    }
    return true;
}

function renderAdminSidebar(activePage) {
    const links = [
        { key: "dashboard", label: "Dashboard", icon: "fa-chart-line" },
        { key: "complaints", label: "Complaints", icon: "fa-clipboard-list" },
        { key: "analytics", label: "Analytics", icon: "fa-chart-pie" },
        { key: "users", label: "Users", icon: "fa-users" },
        { key: "profile", label: "Profile", icon: "fa-user-shield" },
    ];

    return `
        <div class="admin-sidebar">
            <h2><i class="fas fa-city"></i> CivicConnect</h2>
            <small class="admin-badge">Admin Panel</small>
            ${links
                .map(
                    (link) => `
                <a href="${ADMIN_PAGES[link.key]}" class="${activePage === link.key ? "active" : ""}">
                    <i class="fas ${link.icon}"></i> ${link.label}
                </a>`
                )
                .join("")}
            <a href="#" id="adminLogoutLink"><i class="fas fa-right-from-bracket"></i> Logout</a>
        </div>
    `;
}

function setupAdminPage(activePage) {
    if (!requireAdmin()) {
        return null;
    }

    const sidebarHost = document.getElementById("adminSidebar");
    if (sidebarHost) {
        sidebarHost.innerHTML = renderAdminSidebar(activePage);
        const logoutLink = document.getElementById("adminLogoutLink");
        if (logoutLink) {
            logoutLink.addEventListener("click", function (event) {
                event.preventDefault();
                clearAdminSession();
                window.location.href = "index.html";
            });
        }
    }

    const admin = getStoredAdmin();
    const nameEl = document.getElementById("adminWelcomeName");
    if (nameEl && admin) {
        nameEl.textContent = admin.full_name;
    }

    return admin;
}

function setupAdminAnalyticsLayout() {
    const isCitizenLoggedIn =
        localStorage.getItem("civicconnectLoggedIn") === "true";

    if (!isAdminLoggedIn() || isCitizenLoggedIn) {
        return false;
    }

    document.body.classList.add("admin-analytics-mode");

    const sidebarHost = document.createElement("div");
    sidebarHost.id = "adminSidebar";
    document.body.insertBefore(sidebarHost, document.body.firstChild);
    sidebarHost.innerHTML = renderAdminSidebar("analytics");

    const citizenNav = document.querySelector("body > nav");
    if (citizenNav) {
        citizenNav.style.display = "none";
    }

    const logoutLink = document.getElementById("adminLogoutLink");
    if (logoutLink) {
        logoutLink.addEventListener("click", function (event) {
            event.preventDefault();
            clearAdminSession();
            window.location.href = "index.html";
        });
    }

    return true;
}

function priorityClass(priority) {
    const value = (priority || "").toLowerCase();
    if (value === "high") return "high";
    if (value === "medium") return "medium";
    return "low";
}

function statusClass(status) {
    const value = (status || "").toLowerCase();
    if (value === "completed") return "resolved";
    if (value.includes("progress")) return "progress";
    if (value.includes("assigned") || value.includes("review")) return "progress";
    return "pending";
}
