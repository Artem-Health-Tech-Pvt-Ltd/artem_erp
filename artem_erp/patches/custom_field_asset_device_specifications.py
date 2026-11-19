# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters

DEFAULT_DEVICE_TEMPLATES = {
	"Laptop": {
		"prefix": "LAP",
		"series": "LAP-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "CPU", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "RAM", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Storage", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "OS",
				"data_type": "Select",
				"options": "Windows 11\nWindows 10\nmacOS\nUbuntu 24.04\nLinux",
				"default_value": "Windows 11",
				"is_mandatory": 0,
			},
		],
	},
	"Desktop": {
		"prefix": "DESK",
		"series": "DESK-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "CPU", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "RAM", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Storage", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "OS",
				"data_type": "Select",
				"options": "Windows 11\nWindows 10\nUbuntu 24.04\nLinux",
				"default_value": "Windows 11",
				"is_mandatory": 0,
			},
		],
	},
	"Server": {
		"prefix": "SRV",
		"series": "SRV-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "CPU", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "RAM", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Storage", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "OS", "data_type": "Data", "is_mandatory": 0},
			{"spec_name": "IP Address", "data_type": "Data", "is_mandatory": 0},
		],
	},
	"Screen": {
		"prefix": "SCR",
		"series": "SCR-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Screen Size", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Resolution",
				"data_type": "Select",
				"options": "1920x1080 (FHD)\n2560x1440 (2K QHD)\n3840x2160 (4K UHD)",
				"is_mandatory": 0,
			},
		],
	},
	"Mouse-Keyboard": {
		"prefix": "MK",
		"series": "MK-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Type",
				"data_type": "Select",
				"options": "Combo\nMouse\nKeyboard",
				"default_value": "Combo",
				"is_mandatory": 0,
			},
			{
				"spec_name": "Connectivity",
				"data_type": "Select",
				"options": "Wireless 2.4GHz\nBluetooth\nWired USB",
				"is_mandatory": 0,
			},
		],
	},
	"USB Hub": {
		"prefix": "HUB",
		"series": "HUB-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Port Count", "data_type": "Int", "is_mandatory": 0},
			{
				"spec_name": "Power Delivery",
				"data_type": "Select",
				"options": "Yes\nNo",
				"is_mandatory": 0,
			},
		],
	},
	"HDMI": {
		"prefix": "HDMI",
		"series": "HDMI-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Length", "data_type": "Data", "is_mandatory": 0},
		],
	},
	"Headphone": {
		"prefix": "HP",
		"series": "HP-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Connectivity",
				"data_type": "Select",
				"options": "Bluetooth\n3.5mm Jack\nUSB-C",
				"is_mandatory": 0,
			},
		],
	},
	"Charger": {
		"prefix": "CHG",
		"series": "CHG-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Wattage", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Connector Type",
				"data_type": "Select",
				"options": "Type-C\nMagSafe 3\nBarrel Pin",
				"is_mandatory": 1,
			},
		],
	},
	"Printer": {
		"prefix": "PRN",
		"series": "PRN-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Print Technology",
				"data_type": "Select",
				"options": "Laser\nInkjet\nThermal",
				"is_mandatory": 0,
			},
		],
	},
	"TV": {
		"prefix": "TV",
		"series": "TV-.####",
		"specs": [
			{"spec_name": "Manufacturer", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Model", "data_type": "Data", "is_mandatory": 1},
			{"spec_name": "Screen Size", "data_type": "Data", "is_mandatory": 1},
			{
				"spec_name": "Resolution",
				"data_type": "Select",
				"options": "4K UHD\nFull HD\n8K",
				"is_mandatory": 0,
			},
		],
	},
}


def execute():
	# 1. Clean up any legacy custom fields
	for dt, field in [
		("Asset", "custom_warranty_start_date"),
		("Asset", "custom_warranty_end_date"),
		("Asset", "custom_attachment"),
		("Asset", "custom_purchase_and_warranty_details"),
		("Asset", "custom_purchase_and_warranty_col_break"),
		("Asset", "custom_purchase_details"),
		("Asset", "custom_invoice_no"),
		("Asset", "custom_invoice_date"),
		("Asset", "custom_purchase_col_break"),
		("Asset", "custom_invoice_document"),
	]:
		if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": field}):
			frappe.db.delete("Custom Field", {"dt": dt, "fieldname": field})

	# 2. Create updated custom fields for Asset Category and Asset
	custom_fields_to_sync = {
		"Asset Category": CUSTOM_FIELDS.get("Asset Category", []),
		"Asset": CUSTOM_FIELDS.get("Asset", []),
	}
	create_custom_fields(custom_fields_to_sync, update=True, ignore_validate=True)

	# 3. Apply Property Setters (hidden fields on Asset Category and Asset)
	for property_setter in get_property_setters():
		if property_setter.get("doctype") in ["Asset", "Asset Category"]:
			frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)

	# 4. Seed / Update configurations on Asset Category records
	seed_asset_category_specifications()


def seed_asset_category_specifications():
	"""Populate Series Prefix, Naming Series, and Specifications directly on Asset Category records."""
	for category, data in DEFAULT_DEVICE_TEMPLATES.items():
		if not frappe.db.exists("Asset Category", category):
			continue

		cat_doc = frappe.get_doc("Asset Category", category)

		# Set Series Prefix and Asset Series
		if not cat_doc.get("custom_series_prefix") and data.get("prefix"):
			cat_doc.custom_series_prefix = data["prefix"]
		if not cat_doc.get("custom_asset_series") and data.get("series"):
			cat_doc.custom_asset_series = data["series"]

		# Set Specifications if not already configured
		if not cat_doc.get("custom_specifications") and data.get("specs"):
			for item in data["specs"]:
				cat_doc.append("custom_specifications", item)

		cat_doc.save(ignore_permissions=True)
		frappe.db.commit()
