(function () {
    "use strict";

    const chartColors = ["#2563eb", "#16803d", "#b45309", "#b91c1c", "#0f766e", "#7c3aed"];

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function chartPayload() {
        const node = document.getElementById("dashboard-chart-data");
        if (!node) return null;
        try {
            return JSON.parse(node.textContent);
        } catch (error) {
            return null;
        }
    }

    function doughnutChart(id, data) {
        const canvas = document.getElementById(id);
        if (!canvas || !window.Chart || !data) return;
        new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: data.colors && data.colors.length ? data.colors : chartColors,
                    borderWidth: 0,
                }],
            },
            options: {
                maintainAspectRatio: false,
                cutout: "64%",
                plugins: {
                    legend: { display: false },
                },
            },
        });
    }

    function barChart(payload) {
        const canvas = document.getElementById("financeBudgetChart");
        if (!canvas || !window.Chart || !payload) return;
        new Chart(canvas, {
            type: "bar",
            data: {
                labels: payload.labels,
                datasets: [{
                    label: "UGX",
                    data: payload.values,
                    backgroundColor: ["#2563eb", "#16803d", "#b91c1c", "#2563eb", "#b45309", "#16803d"],
                    borderRadius: 6,
                }],
            },
            options: {
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return Number(value).toLocaleString();
                            },
                        },
                    },
                },
            },
        });
    }

    function trendCharts(payload) {
        if (!window.Chart || !payload) return;
        document.querySelectorAll("[data-trend-chart]").forEach(function (canvas) {
            const index = Number(canvas.getAttribute("data-trend-chart"));
            const dataset = payload.datasets && payload.datasets[index];
            if (!dataset) return;
            new Chart(canvas, {
                type: "line",
                data: {
                    labels: payload.labels,
                    datasets: [{
                        label: dataset.label,
                        data: dataset.values,
                        borderColor: chartColors[index % chartColors.length],
                        backgroundColor: "rgba(37, 99, 235, 0.12)",
                        pointRadius: 3,
                        tension: 0.35,
                        fill: true,
                    }],
                },
                options: {
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { precision: 0 },
                        },
                    },
                },
            });
        });
    }

    function initCharts() {
        const payload = chartPayload();
        if (!payload) return;
        doughnutChart("departmentMixChart", payload.department);
        doughnutChart("severityChart", payload.severity);
        barChart(payload.finance);
        trendCharts(payload.trends);
    }

    function initDataTables() {
        if (!window.DataTable) return;
        document.querySelectorAll("[data-erp-table], .data-table").forEach(function (table) {
            if (table.dataset.enhancedTable === "true") return;
            table.dataset.enhancedTable = "true";
            const firstHeader = table.querySelector("thead th:first-child");
            const columnDefs = [
                { targets: -1, orderable: false, searchable: false },
            ];
            if (firstHeader && firstHeader.querySelector('input[type="checkbox"]')) {
                columnDefs.push({ targets: 0, orderable: false, searchable: false });
            }
            new DataTable(table, {
                pageLength: 25,
                order: [],
                columnDefs: columnDefs,
                language: {
                    search: "",
                    searchPlaceholder: "Search records",
                },
            });
        });
    }

    function initSweetAlerts() {
        if (!window.Swal) return;
        document.querySelectorAll(".message").forEach(function (message) {
            const text = message.textContent.trim();
            if (!text) return;
            Swal.fire({
                toast: true,
                position: "top-end",
                icon: "success",
                title: text,
                showConfirmButton: false,
                timer: 3200,
                timerProgressBar: true,
            });
        });
        document.addEventListener("click", function (event) {
            const deleteLink = event.target.closest('a[href$="/delete/"]');
            if (!deleteLink) return;
            event.preventDefault();
            Swal.fire({
                title: "Delete this record?",
                text: "This action opens the delete confirmation page.",
                icon: "warning",
                showCancelButton: true,
                confirmButtonText: "Continue",
                confirmButtonColor: "#b91c1c",
            }).then(function (result) {
                if (result.isConfirmed) {
                    window.location.href = deleteLink.href;
                }
            });
        });
    }

    function initHtmx() {
        if (!window.htmx) return;
        document.body.addEventListener("htmx:configRequest", function (event) {
            const token = csrfToken();
            if (token) event.detail.headers["X-CSRFToken"] = token;
        });
    }

    ready(function () {
        initHtmx();
        initCharts();
        initDataTables();
        initSweetAlerts();
    });
})();
