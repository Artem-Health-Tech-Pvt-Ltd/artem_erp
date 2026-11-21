frappe.provide("artem_erp");

// 1. If on login page, remove generic '?redirect-to=/desk' so login response home_page is respected
(function handle_login_redirect_param() {
	if (
		typeof window !== "undefined" &&
		window.location &&
		window.location.pathname.includes("/login")
	) {
		try {
			const params = new URLSearchParams(window.location.search);
			const redirectTo = params.get("redirect-to");
			if (
				redirectTo === "/desk" ||
				redirectTo === "desk" ||
				redirectTo === "/desk/" ||
				redirectTo === "desk/"
			) {
				params.delete("redirect-to");
				const newSearch = params.toString() ? "?" + params.toString() : "";
				window.history.replaceState(
					{},
					"",
					window.location.pathname + newSearch + window.location.hash
				);
			}
		} catch (e) {
			// ignore parameter sanitization errors
		}
	}
})();

// Center logo and header on Sign In / Login page
(function center_login_logo() {
	if (
		typeof window !== "undefined" &&
		window.location &&
		window.location.pathname.includes("/login")
	) {
		const apply_center = function () {
			$(".page-card-head").css({
				"align-items": "center",
				"text-align": "center",
			});
			$(".page-card-head img.app-logo").css({
				"margin-left": "auto",
				"margin-right": "auto",
				"align-self": "center",
				display: "block",
				"max-height": "48px",
				width: "auto",
			});
			$(
				".page-card-head .page-card-head-text, .page-card-head h4, .page-card-head .page-card-subtitle"
			).css({
				"text-align": "center",
				"align-items": "center",
			});
		};

		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", apply_center);
		} else {
			apply_center();
		}
		if (typeof $ !== "undefined") {
			$(document).ready(apply_center);
		}
	}
})();

// 2. Direct open Employee Dashboard Workspace on login / desk landing
artem_erp.redirect_to_employee_dashboard = function () {
	if (
		!frappe.session ||
		frappe.session.user === "Guest" ||
		frappe.session.user === "Administrator"
	)
		return;

	const roles = frappe.user_roles || [];
	if (!roles.includes("Employee") && !roles.includes("Manager")) return;

	// Users with full HR or System access have broader responsibilities
	if (
		roles.includes("System Manager") ||
		roles.includes("HR Manager") ||
		roles.includes("HR User")
	) {
		return;
	}

	const route = frappe.get_route();
	if (!route || route.length === 0 || route[0] === "desktop" || route[0] === "") {
		frappe.set_route("desk", "employee-dashboard");
	}
};

$(document).on("app_ready desk_ready", artem_erp.redirect_to_employee_dashboard);
if (frappe.router) {
	frappe.router.on("change", artem_erp.redirect_to_employee_dashboard);
}

// 3. Ensure company logo is displayed in Sidebar Header and Desktop Icon
artem_erp.setup_company_logo_in_sidebar_and_navbar = function () {
	const logo_url = "/assets/artem_erp/images/artem_logo.png";
	const logo_img_sidebar = `<img src="${logo_url}" alt="Logo" style="width: 100%; height: 100%; object-fit: contain;">`;

	// Update in-memory boot & desktop icons
	try {
		if (frappe.boot && frappe.boot.desktop_icons) {
			frappe.boot.desktop_icons.forEach(function (item) {
				if (item.label === "Employee Dashboard" || item.name === "Employee Dashboard") {
					item.logo_url = logo_url;
					item.icon_image = logo_url;
					item.app = "artem_erp";
				}
			});
		}
		if (frappe.desktop_icons) {
			frappe.desktop_icons.forEach(function (item) {
				if (item.label === "Employee Dashboard" || item.name === "Employee Dashboard") {
					item.logo_url = logo_url;
					item.icon_image = logo_url;
					item.app = "artem_erp";
				}
			});
		}
		if (frappe.session && frappe.session.user) {
			const user_key = `${frappe.session.user}:desktop`;
			let layout_str = localStorage.getItem(user_key);
			if (layout_str) {
				let layout = JSON.parse(layout_str);
				let updated = false;
				if (Array.isArray(layout)) {
					layout.forEach(function (item) {
						if (
							item.label === "Employee Dashboard" ||
							item.name === "Employee Dashboard"
						) {
							if (item.logo_url !== logo_url || item.icon_image !== logo_url) {
								item.logo_url = logo_url;
								item.icon_image = logo_url;
								item.app = "artem_erp";
								updated = true;
							}
						}
					});
					if (updated) {
						localStorage.setItem(user_key, JSON.stringify(layout));
					}
				}
			}
		}
	} catch (e) {
		// ignore
	}

	// A. Hook SidebarHeader prototype so future renders/switches use the company logo
	if (frappe.ui && frappe.ui.SidebarHeader && !frappe.ui.SidebarHeader._artem_patched) {
		frappe.ui.SidebarHeader._artem_patched = true;
		const orig_set_header_icon = frappe.ui.SidebarHeader.prototype.set_header_icon;
		frappe.ui.SidebarHeader.prototype.set_header_icon = function () {
			orig_set_header_icon.apply(this, arguments);
			if (
				this.sidebar?.sidebar_title === "Employee Dashboard" ||
				!this.header_icon ||
				typeof this.header_icon !== "string" ||
				!this.header_icon.includes("<img") ||
				this.header_icon.includes("frappe-framework-logo") ||
				this.header_icon.includes("employee_dashboard.svg")
			) {
				this.header_icon = logo_img_sidebar;
			}
		};
	}

	// B. Direct DOM update for currently rendered sidebar header
	$(".sidebar-header .header-logo, .sidebar-item-icon .header-logo").each(function () {
		let img = $(this).find("img");
		if (
			!img.length ||
			!img.attr("src") ||
			img.attr("src").includes("employee_dashboard.svg") ||
			img.attr("src").includes("frappe-framework-logo")
		) {
			$(this).html(logo_img_sidebar);
		}
	});

	// C. Desktop Icon on /desk: ensure Employee Dashboard displays Artem logo
	$(".desktop-icon[data-id='Employee Dashboard']").each(function () {
		let container = $(this).find(".icon-container");
		if (!container.length) {
			$(this).prepend(
				`<div class="icon-container" style="background-color: transparent !important;"><img class="app-icon" src="${logo_url}" alt="Employee Dashboard" style="width: 100%; height: 100%; object-fit: contain;"></div>`
			);
			$(this).find("> svg").remove();
		} else {
			container.css("background-color", "transparent");
			let img = container.find("img");
			if (!img.length || img.attr("src") !== logo_url) {
				container.html(
					`<img class="app-icon" src="${logo_url}" alt="Employee Dashboard" style="width: 100%; height: 100%; object-fit: contain;">`
				);
			}
		}
	});
};

$(document).on(
	"app_ready desk_ready page-change route-change",
	artem_erp.setup_company_logo_in_sidebar_and_navbar
);
if (frappe.router) {
	frappe.router.on("change", artem_erp.setup_company_logo_in_sidebar_and_navbar);
}

// Observe desktop page renders to guarantee Employee Dashboard logo is displayed
(function observe_desktop_icons() {
	if (typeof MutationObserver !== "undefined") {
		const observer = new MutationObserver(function () {
			const desk_icon = $(".desktop-icon[data-id='Employee Dashboard']");
			if (desk_icon.length) {
				const logo_url = "/assets/artem_erp/images/artem_logo.png";
				let container = desk_icon.find(".icon-container");
				let img = container.find("img");
				if (!img.length || img.attr("src") !== logo_url) {
					container.css("background-color", "transparent");
					container.html(
						`<img class="app-icon" src="${logo_url}" alt="Employee Dashboard" style="width: 100%; height: 100%; object-fit: contain;">`
					);
				}
			}
		});

		const start_observing = function () {
			const target = document.getElementById("page-desktop") || document.body;
			if (target) {
				observer.observe(target, { childList: true, subtree: true });
			}
		};

		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", start_observing);
		} else {
			start_observing();
		}
	}
})();
