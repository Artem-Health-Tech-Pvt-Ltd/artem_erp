// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.pages["asset_management_dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Asset Management Dashboard"),
		single_column: true,
	});

	page.asset_dashboard = new AssetManagementDashboard(page);
};

class AssetManagementDashboard {
	constructor(page) {
		this.page = page;
		this.charts = {};
		this.filters = {
			asset_category: "",
			status: "",
			company: "",
			location: "",
		};

		this.setup_actions();
		this.setup_filters();
		this.setup_container();
		this.refresh();
	}

	setup_actions() {
		this.page.set_primary_action(
			__("Assign Assets"),
			() => {
				frappe.set_route("List", "Employee Asset Allocation");
			},
			"octicon octicon-plus"
		);

		this.page.add_button(__("Allocation Report"), () => {
			frappe.set_route("query-report", "Employee-wise Asset Allocation Report");
		});

		this.page.add_button(
			__("Refresh"),
			() => {
				this.refresh();
			},
			"octicon octicon-sync"
		);
	}

	setup_filters() {
		let me = this;

		this.cat_filter = this.page.add_field({
			fieldname: "asset_category",
			label: __("Category"),
			fieldtype: "Link",
			options: "Asset Category",
			change: function () {
				me.filters.asset_category = this.get_value();
				me.refresh();
			},
		});

		this.status_filter = this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nIn Stock\nAssigned\nIn Repair",
			change: function () {
				me.filters.status = this.get_value();
				me.refresh();
			},
		});

		this.company_filter = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			change: function () {
				me.filters.company = this.get_value();
				me.refresh();
			},
		});

		this.location_filter = this.page.add_field({
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Location",
			change: function () {
				me.filters.location = this.get_value();
				me.refresh();
			},
		});
	}

	setup_container() {
		this.container = $(`
			<div class="asset-dashboard-container">
				<!-- KPI Cards Grid -->
				<div class="asset-cards-grid" id="kpi-cards"></div>

				<!-- Charts Row 1 -->
				<div class="asset-charts-row">
					<div class="asset-chart-card">
						<div class="chart-header">
							<span>${__("Category-wise Total Assets")}</span>
						</div>
						<div id="chart-category-bar" style="height: 280px;"></div>
					</div>
					<div class="asset-chart-card">
						<div class="chart-header">
							<span>${__("Overall Status Distribution")}</span>
						</div>
						<div id="chart-status-donut" style="height: 280px;"></div>
					</div>
				</div>

				<!-- Charts Row 2 -->
				<div class="asset-charts-row">
					<div class="asset-chart-card">
						<div class="chart-header">
							<span>${__("Category vs Status Breakdown")}</span>
						</div>
						<div id="chart-category-status" style="height: 280px;"></div>
					</div>
					<div class="asset-chart-card">
						<div class="chart-header">
							<span>${__("Asset Availability Ratio")}</span>
						</div>
						<div id="chart-availability-donut" style="height: 280px;"></div>
					</div>
				</div>

				<!-- Category-wise Distribution Table -->
				<div class="asset-table-section">
					<div class="asset-table-header">
						<h5>${__("Asset Category-wise Status Breakdown")}</h5>
						<span class="text-muted" style="font-size: 12px;">${__(
							"Click on any category to view its assets"
						)}</span>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered table-hover category-table">
							<thead>
								<tr>
									<th>${__("Asset Category")}</th>
									<th class="text-right">${__("Total Assets")}</th>
									<th class="text-right">${__("In Stock")}</th>
									<th class="text-right">${__("Assigned")}</th>
									<th class="text-right">${__("In Repair")}</th>
									<th class="text-right">${__("Availability %")}</th>
								</tr>
							</thead>
							<tbody id="category-table-body"></tbody>
						</table>
					</div>
				</div>

				<!-- Recent Allocations Table -->
				<div class="asset-table-section">
					<div class="asset-table-header">
						<h5>${__("Recent Asset Allocation & Return Activities")}</h5>
						<button class="btn btn-xs btn-default" id="btn-view-all-history">${__(
							"View Complete History"
						)}</button>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered category-table">
							<thead>
								<tr>
									<th>${__("Asset")}</th>
									<th>${__("Category")}</th>
									<th>${__("Employee")}</th>
									<th>${__("Status")}</th>
									<th>${__("Date")}</th>
								</tr>
							</thead>
							<tbody id="recent-table-body"></tbody>
						</table>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.container.find("#btn-view-all-history").on("click", () => {
			frappe.set_route("List", "Asset Assignment History");
		});
	}

	refresh() {
		let me = this;
		frappe.call({
			method: "artem_erp.artem_erp.page.asset_management_dashboard.asset_management_dashboard.get_dashboard_data",
			args: {
				filters: me.filters,
			},
			callback: function (r) {
				if (r.message) {
					me.render_kpi_cards(r.message.cards);
					me.render_category_table(r.message.category_table);
					me.render_charts(r.message.charts);
					me.render_recent_assignments(r.message.recent_assignments);
				}
			},
		});
	}

	render_kpi_cards(cards) {
		let html = `
			<div class="asset-kpi-card border-primary" data-action="all">
				<div class="card-label">
					<span>${__("Total Assets")}</span>
					<i class="fa fa-cubes text-primary"></i>
				</div>
				<div class="card-value">${cards.total_assets}</div>
				<div class="card-subtext">${__("All registered assets")}</div>
			</div>

			<div class="asset-kpi-card border-success" data-action="in_stock">
				<div class="card-label">
					<span>${__("In Stock")}</span>
					<i class="fa fa-check-circle text-success"></i>
				</div>
				<div class="card-value">${cards.in_stock}</div>
				<div class="card-subtext">${cards.availability_pct}% ${__("available for assignment")}</div>
			</div>

			<div class="asset-kpi-card border-info" data-action="assigned">
				<div class="card-label">
					<span>${__("Assigned")}</span>
					<i class="fa fa-user-check text-info"></i>
				</div>
				<div class="card-value">${cards.assigned}</div>
				<div class="card-subtext">${__("Assigned to employees")}</div>
			</div>

			<div class="asset-kpi-card border-warning" data-action="in_repair">
				<div class="card-label">
					<span>${__("In Repair")}</span>
					<i class="fa fa-wrench text-warning"></i>
				</div>
				<div class="card-value">${cards.in_repair}</div>
				<div class="card-subtext">${__("Under maintenance/repair")}</div>
			</div>

			<div class="asset-kpi-card border-purple" data-action="categories">
				<div class="card-label">
					<span>${__("Categories")}</span>
					<i class="fa fa-tags text-success"></i>
				</div>
				<div class="card-value">${cards.total_categories}</div>
				<div class="card-subtext">${__("Configured categories")}</div>
			</div>

			<div class="asset-kpi-card border-dark" data-action="employees">
				<div class="card-label">
					<span>${__("Custodians")}</span>
					<i class="fa fa-users text-dark"></i>
				</div>
				<div class="card-value">${cards.employees_with_assets}</div>
				<div class="card-subtext">${__("Employees with assets")}</div>
			</div>
		`;

		let $cards = this.container.find("#kpi-cards").html(html);

		$cards.find(".asset-kpi-card").on("click", function () {
			let action = $(this).data("action");
			if (action === "all") {
				frappe.set_route("List", "Asset");
			} else if (action === "in_stock") {
				frappe.set_route("List", "Asset", { custom_asset_status: "In Stock" });
			} else if (action === "assigned") {
				frappe.set_route("List", "Asset", { custom_asset_status: "Assigned" });
			} else if (action === "in_repair") {
				frappe.set_route("List", "Asset", { custom_asset_status: "In Repair" });
			} else if (action === "categories") {
				frappe.set_route("List", "Asset Category");
			} else if (action === "employees") {
				frappe.set_route("List", "Employee Asset Allocation");
			}
		});
	}

	render_category_table(categories) {
		let $tbody = this.container.find("#category-table-body").empty();

		if (!categories || categories.length === 0) {
			$tbody.html(
				`<tr><td colspan="6" class="text-center text-muted">${__(
					"No assets found matching filters"
				)}</td></tr>`
			);
			return;
		}

		categories.forEach((cat) => {
			let badge_class = cat.availability_pct > 30 ? "text-success" : "text-danger";
			let row = $(`
				<tr class="clickable-row">
					<td><strong>${cat.category}</strong></td>
					<td class="text-right"><strong>${cat.total}</strong></td>
					<td class="text-right text-success">${cat.in_stock}</td>
					<td class="text-right text-primary">${cat.assigned}</td>
					<td class="text-right text-warning">${cat.in_repair}</td>
					<td class="text-right ${badge_class}">${cat.availability_pct}%</td>
				</tr>
			`).appendTo($tbody);

			row.on("click", () => {
				frappe.set_route("List", "Asset", { asset_category: cat.category });
			});
		});
	}

	render_charts(charts_data) {
		// Chart 1: Category Distribution (Bar)
		let el1 = this.container.find("#chart-category-bar")[0];
		if (el1 && charts_data.category_distribution.labels.length > 0) {
			this.charts.cat_bar = new frappe.Chart(el1, {
				title: "",
				data: charts_data.category_distribution,
				type: "bar",
				height: 250,
				colors: ["#3e97ff"],
				barOptions: { spaceRatio: 0.4 },
			});
		}

		// Chart 2: Status Distribution (Donut)
		let el2 = this.container.find("#chart-status-donut")[0];
		if (el2) {
			this.charts.status_donut = new frappe.Chart(el2, {
				title: "",
				data: charts_data.status_distribution,
				type: "donut",
				height: 250,
				colors: ["#17c653", "#1b84ff", "#f6c000"],
			});
		}

		// Chart 3: Category vs Status (Stacked Bar)
		let el3 = this.container.find("#chart-category-status")[0];
		if (el3 && charts_data.category_vs_status.labels.length > 0) {
			this.charts.cat_status = new frappe.Chart(el3, {
				title: "",
				data: charts_data.category_vs_status,
				type: "bar",
				height: 250,
				stacked: 1,
				colors: ["#17c653", "#1b84ff", "#f6c000"],
			});
		}

		// Chart 4: Availability Ratio (Donut)
		let el4 = this.container.find("#chart-availability-donut")[0];
		if (el4) {
			this.charts.avail_donut = new frappe.Chart(el4, {
				title: "",
				data: charts_data.availability,
				type: "donut",
				height: 250,
				colors: ["#17c653", "#7239ea"],
			});
		}
	}

	render_recent_assignments(records) {
		let $tbody = this.container.find("#recent-table-body").empty();

		if (!records || records.length === 0) {
			$tbody.html(
				`<tr><td colspan="5" class="text-center text-muted">${__(
					"No recent assignment records found"
				)}</td></tr>`
			);
			return;
		}

		records.forEach((r) => {
			let badge =
				r.assignment_status === "Assigned"
					? `<span class="indicator-badge assigned">${__("Assigned")}</span>`
					: `<span class="indicator-badge in-stock">${__("Returned")}</span>`;

			let date_str = frappe.datetime.str_to_user(r.assignment_date);

			let $tr = $(`
				<tr>
					<td><a href="/app/asset/${r.asset}">${r.asset}</a> <span class="text-muted">(${
				r.asset_name || ""
			})</span></td>
					<td>${r.asset_category || ""}</td>
					<td><a href="/app/employee/${r.employee}">${r.employee_name || r.employee}</a></td>
					<td>${badge}</td>
					<td>${date_str}</td>
				</tr>
			`).appendTo($tbody);
		});
	}
}
