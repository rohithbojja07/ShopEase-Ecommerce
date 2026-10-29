(() => {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const money = (value) => {
        const number = Number(value || 0);
        return Number.isFinite(number)
            ? number.toLocaleString("en-IN", { style: "currency", currency: "INR" })
            : "₹0.00";
    };
    const number = (value) => Number(value || 0).toLocaleString("en-IN");

    async function api(path) {
        const response = await fetch(path, {
            method: "GET",
            credentials: "same-origin",
            headers: {
                Accept: "application/json"
            }
        });

        if (!response.ok) {
            const error = new Error(`Request failed (${response.status})`);
            error.status = response.status;
            throw error;
        }

        return response.json();
    }

    function showMessage(message, type = "info") {
        const box = $("dashboardMessage");
        box.className = `alert alert-${type}`;
        box.textContent = message;
    }

    function renderTable(id, rows, emptyMessage, renderRow, colspan) {
        const target = $(id);
        if (!rows || !rows.length) {
            target.innerHTML = `<tr><td colspan="${colspan}" class="empty-state">${emptyMessage}</td></tr>`;
            return;
        }
        target.innerHTML = rows.map(renderRow).join("");
    }

    function cell(value) {
        const td = document.createElement("td");
        td.textContent = value == null ? "—" : String(value);
        return td;
    }

    function renderSalesChart(series) {
        const target = $("salesChart");
        target.replaceChildren();

        if (!series.length) {
            target.textContent = "No sales data available for this period.";
            return;
        }

        const values = series.map((item) => Number(item.revenue || 0));
        const max = Math.max(...values, 1);

        series.forEach((item) => {
            const column = document.createElement("div");
            column.className = "chart-column";
            column.title = `${item.period}: ${money(item.revenue)} · ${item.orders} orders`;

            const bar = document.createElement("div");
            bar.className = "chart-bar";
            bar.style.height = `${Math.max(2, Number(item.revenue || 0) / max * 170)}px`;
            bar.setAttribute("role", "img");
            bar.setAttribute("aria-label", `${item.period}, ${money(item.revenue)}`);

            const label = document.createElement("span");
            label.className = "chart-label";
            label.textContent = item.period;

            column.append(bar, label);
            target.append(column);
        });
    }

    async function loadSales() {
        const period = $("salesPeriod").value;
        const [dashboard, series, statuses] = await Promise.all([
            api("/api/admin/analytics/dashboard/"),
            api(`/api/admin/analytics/sales/?period=${encodeURIComponent(period)}`),
            api("/api/admin/analytics/order-status/")
        ]);

        $("revenueMetric").textContent = money(dashboard.revenue);
        $("todayRevenueMetric").textContent = money(dashboard.todays_revenue);
        $("monthRevenueMetric").textContent = money(dashboard.monthly_revenue);
        $("ordersMetric").textContent = number(dashboard.total_orders);
        $("customersMetric").textContent = number(dashboard.total_customers);
        $("productsMetric").textContent = number(dashboard.total_products);

        renderSalesChart(series.series || []);

        renderTable(
            "orderStatusTable",
            statuses.results || [],
            "No orders found.",
            (item) => `<tr><td>${item.label}</td><td>${number(item.count)}</td></tr>`,
            2
        );

        renderTable(
            "lowStockTable",
            dashboard.low_stock_items || [],
            "No low-stock variants.",
            (item) => `<tr><td>${item.product}<br><small class="text-secondary">${item.sku}</small></td><td>${number(item.available)} / ${number(item.threshold)}</td></tr>`,
            2
        );
    }

    async function loadProducts() {
        const data = await api("/api/admin/analytics/products/?limit=10");
        const rows = data.best_selling || [];

        renderTable(
            "productTable",
            rows,
            "No product data available.",
            (item) => `<tr><td>${escapeHtml(item.name)}</td><td>${number(item.units_sold)}</td><td>${money(item.revenue)}</td><td>${number(item.views)}</td><td>${item.average_rating == null ? "—" : item.average_rating}</td><td>${number(item.review_count)}</td></tr>`,
            6
        );
    }

    async function loadCustomers() {
        const data = await api("/api/admin/analytics/customers/?days=30&limit=10");

        $("newCustomersMetric").textContent = number(data.new_this_month);
        $("returningCustomersMetric").textContent = number(data.returning_customers);
        $("repeatRateMetric").textContent = `${Number(data.repeat_rate_percent || 0).toFixed(1)}%`;
        $("averageOrdersMetric").textContent = Number(data.average_orders_per_customer || 0).toFixed(2);

        renderTable(
            "customerTable",
            data.top_customers || [],
            "No customer spending data available.",
            (item) => `<tr><td>${escapeHtml(item.email)}</td><td>${number(item.orders)}</td><td>${money(item.net_spent)}</td></tr>`,
            3
        );
    }

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (character) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[character]);
    }

    async function loadDashboard() {
        showMessage("Loading analytics...");
        const results = await Promise.allSettled([
            loadSales(),
            loadProducts(),
            loadCustomers()
        ]);

        const failed = results.filter((result) => result.status === "rejected");
        const denied = failed.some((result) =>
            result.reason && (result.reason.status === 401 || result.reason.status === 403)
        );

        if (denied) {
            showMessage(
                "Some analytics are unavailable for your staff role. Check your assigned analytics permissions.",
                "warning"
            );
        } else if (failed.length) {
            showMessage(
                `${failed.length} analytics section(s) could not load. Refresh the page or check the server logs.`,
                "warning"
            );
        } else {
            showMessage("Analytics updated successfully.", "success");
        }

        $("salesSection").hidden = results[0].status === "rejected";
        $("productsSection").hidden = results[1].status === "rejected";
        $("customersSection").hidden = results[2].status === "rejected";
    }

    $("refreshDashboard").addEventListener("click", loadDashboard);
    $("salesPeriod").addEventListener("change", async () => {
        try {
            const data = await api(`/api/admin/analytics/sales/?period=${encodeURIComponent($("salesPeriod").value)}`);
            renderSalesChart(data.series || []);
        } catch (error) {
            showMessage("Could not load the selected sales period.", "warning");
        }
    });

    loadDashboard();
})();

