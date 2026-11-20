# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _


def validate(doc, method=None):
	"""Server-side validation for Asset Category IT Asset Configuration:
	1. Prefix format (uppercase, letters/digits, 2-5 chars).
	2. Build asset_series (e.g. LAP-.####).
	3. Prefix uniqueness across categories.
	4. Prefix lock: cannot change if Assets already exist under this category.
	5. Specification rules: unique spec_name, valid Select options, typed default_value.
	"""
	validate_series_prefix(doc)
	validate_specifications(doc)


def validate_series_prefix(doc):
	if getattr(frappe.flags, "in_install", False) or getattr(frappe.flags, "in_migrate", False):
		return

	prefix = (doc.get("custom_series_prefix") or "").strip().upper()
	if not prefix:
		frappe.throw(_("Series Prefix is mandatory (e.g. LAP, DESK, AHT-LAP-AMD)."))

	# Allow alphanumeric codes separated by hyphens (e.g. LAP, DESK, AHT-LAP-AMD)
	if not re.match(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$", prefix):
		frappe.throw(
			_(
				"Series Prefix '{0}' is invalid. It must contain only uppercase alphanumeric characters separated by single hyphens (e.g. LAP, DESK, AHT-LAP-AMD)."
			).format(prefix)
		)

	# Store uppercase prefix
	doc.custom_series_prefix = prefix

	# Auto-build asset_series: e.g. AHT-LAP-AMD-.###
	series = f"{prefix}-.###"
	doc.custom_asset_series = series

	# Prefix uniqueness
	existing = frappe.db.get_value(
		"Asset Category",
		{"custom_series_prefix": prefix, "name": ["!=", doc.name]},
		"name",
	)
	if existing:
		frappe.throw(
			_("Series Prefix '{0}' is already used by Asset Category '{1}'.").format(prefix, existing)
		)

	# Prefix lock: prevent changing if assets exist
	if not doc.is_new():
		old_prefix = frappe.db.get_value("Asset Category", doc.name, "custom_series_prefix")
		if old_prefix and old_prefix.strip().upper() != prefix:
			if frappe.db.exists("Asset", {"asset_category": doc.name}):
				frappe.throw(
					_(
						"Cannot change Series Prefix for Asset Category '{0}' because Assets have already been created with prefix '{1}'. Changing it midway breaks ID continuity."
					).format(doc.name, old_prefix)
				)


def validate_specifications(doc):
	specs = doc.get("custom_specifications") or []
	seen_names = set()

	for row in specs:
		if not row.spec_name or not row.spec_name.strip():
			frappe.throw(_("Row #{0}: Specification Name cannot be empty.").format(row.idx))

		clean_name = row.spec_name.strip().lower()
		if clean_name in seen_names:
			frappe.throw(
				_(
					"Specification '{0}' is defined more than once in this category. Each specification name must be unique."
				).format(row.spec_name.strip())
			)
		seen_names.add(clean_name)

		# Data type validation
		data_type = row.data_type or "Data"
		if data_type == "Select":
			lines = [opt.strip() for opt in (row.options or "").splitlines() if opt.strip()]
			if len(lines) < 2:
				frappe.throw(
					_(
						"Row #{0} ('{1}'): Select Data Type requires at least 2 options (one option per line)."
					).format(row.idx, row.spec_name)
				)
		else:
			row.options = ""

		# Default value type verification
		if row.default_value and str(row.default_value).strip():
			val = str(row.default_value).strip()
			if data_type == "Int":
				try:
					int(val)
				except ValueError:
					frappe.throw(
						_("Row #{0} ('{1}'): Default Value '{2}' is not a valid integer.").format(
							row.idx, row.spec_name, val
						)
					)
			elif data_type == "Float":
				try:
					float(val)
				except ValueError:
					frappe.throw(
						_("Row #{0} ('{1}'): Default Value '{2}' is not a valid number.").format(
							row.idx, row.spec_name, val
						)
					)
			elif data_type == "Date":
				try:
					frappe.utils.getdate(val)
				except Exception:
					frappe.throw(
						_("Row #{0} ('{1}'): Default Value '{2}' is not a valid date (YYYY-MM-DD).").format(
							row.idx, row.spec_name, val
						)
					)
			elif data_type == "Select":
				valid_opts = [opt.strip() for opt in (row.options or "").splitlines() if opt.strip()]
				if val not in valid_opts:
					frappe.throw(
						_(
							"Row #{0} ('{1}'): Default Value '{2}' must match one of the configured options: {3}."
						).format(row.idx, row.spec_name, val, ", ".join(valid_opts))
					)


def create_item(doc, method=None):
	"""on_update hook: Auto-create linked Fixed Asset Item for this category if missing.
	Users never need to manually create or select Items!"""
	default_item = doc.get("custom_default_item")
	if default_item and frappe.db.exists("Item", default_item):
		return

	# Ensure Item Group "Fixed Asset" exists
	if not frappe.db.exists("Item Group", "Fixed Asset"):
		group = frappe.new_doc("Item Group")
		group.item_group_name = "Fixed Asset"
		group.parent_item_group = "All Item Groups"
		group.is_group = 0
		group.flags.ignore_mandatory = True
		group.flags.ignore_validate = True
		group.insert(ignore_permissions=True, ignore_mandatory=True)

	item_code = f"{doc.name} Asset"
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = item_code
		item.item_group = "Fixed Asset"
		item.is_fixed_asset = 1
		item.is_stock_item = 0
		item.is_sales_item = 0
		item.is_purchase_item = 0
		item.asset_category = doc.name
		item.stock_uom = "Nos"

		# If India Compliance / GST is active, populate valid HSN code if present
		if frappe.db.has_column("Item", "gst_hsn_code"):
			hsn = doc.get("custom_hsn_code") or "8471"
			if frappe.db.exists("GST HSN Code", hsn):
				item.gst_hsn_code = hsn
			else:
				first_hsn = frappe.db.get_value("GST HSN Code", {}, "name")
				if first_hsn:
					item.gst_hsn_code = first_hsn

		# Bypass validation and mandatory checks for auto-provisioned internal asset item
		item.flags.ignore_mandatory = True
		item.flags.ignore_validate = True
		item.flags.ignore_permissions = True
		item.insert(ignore_permissions=True, ignore_mandatory=True)

	# Save in custom_default_item
	doc.custom_default_item = item_code
	frappe.db.set_value("Asset Category", doc.name, "custom_default_item", item_code, update_modified=False)
