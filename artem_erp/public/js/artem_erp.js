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
			console.error("Error sanitizing redirect-to parameter:", e);
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
$(document).on("app_ready desk_ready", artem_erp.redirect_to_employee_dashboard);
if (frappe.router) {
	frappe.router.on("change", artem_erp.redirect_to_employee_dashboard);
}
