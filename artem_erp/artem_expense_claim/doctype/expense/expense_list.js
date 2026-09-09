frappe.listview_settings["Expense"] = {
	add_fields: ["is_overlimit__expense"],
	get_indicator: function (doc) {
		if (cint(doc.is_overlimit__expense)) {
			return [__("Over-Limit"), "orange", "is_overlimit__expense,=,1"];
		}
		return [__("Within Limit"), "green", "is_overlimit__expense,=,0"];
	},
	onload: function (listview) {
		// Add custom style once to highlight the row
		if (!document.getElementById("expense-overlimit-style")) {
			const style = document.createElement("style");
			style.id = "expense-overlimit-style";
			style.innerHTML = `
				.expense-overlimit-row {
					background-color: #fff4e5 !important;
					border-left: 4px solid #ff9800 !important;
				}
				.expense-overlimit-row:hover {
					background-color: #ffe8cc !important;
				}
				[data-theme="dark"] .expense-overlimit-row {
					background-color: #3b2a1a !important;
					border-left: 4px solid #ff9800 !important;
				}
				[data-theme="dark"] .expense-overlimit-row:hover {
					background-color: #4a3420 !important;
				}
			`;
			document.head.appendChild(style);
		}
	},
	formatters: {
		is_overlimit__expense: function (val, df, doc) {
			if (cint(val) || cint(doc.is_overlimit__expense)) {
				setTimeout(() => {
					const row = document.querySelector(`.list-row-container [data-name="${doc.name}"]`);
					if (row) {
						row.classList.add("expense-overlimit-row");
					}
				}, 10);
				return `<span class="indicator-pill orange">${__("Over-Limit")}</span>`;
			}
			return `<span class="indicator-pill green">${__("Within Limit")}</span>`;
		},
	},
	refresh: function (listview) {
		setTimeout(() => {
			listview.data.forEach((doc) => {
				if (cint(doc.is_overlimit__expense)) {
					const row = listview.$page.find(`.list-row-container [data-name="${doc.name}"]`);
					if (row.length) {
						row.addClass("expense-overlimit-row");
					}
				}
			});
		}, 100);
	},
};
