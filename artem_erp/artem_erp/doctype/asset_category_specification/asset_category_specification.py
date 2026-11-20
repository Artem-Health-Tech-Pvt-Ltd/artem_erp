# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class AssetCategorySpecification(Document):
	pass


@frappe.whitelist()
def get_next_asset_number(asset_category):
	"""
	Calculates the next sequential number for an asset category based on the
	highest existing number found for that category's prefix.
	Returns:
	{
	    "prefix": "AHT-LAP-AMD",
	    "next_number": "001" or "046",
	    "full_name": "AHT-LAP-AMD-001",
	    "pad_length": 3
	}
	"""
	if not asset_category:
		return {"prefix": "", "next_number": "", "full_name": "", "pad_length": 3}

	prefix = get_category_prefix(asset_category)
	if not prefix:
		return {"prefix": "", "next_number": "", "full_name": "", "pad_length": 3}

	highest_num, pad_len = get_highest_asset_number_and_padding(prefix, asset_category)
	next_num = highest_num + 1
	formatted_number = str(next_num).zfill(pad_len)
	full_name = f"{prefix}-{formatted_number}"

	return {
		"prefix": prefix,
		"next_number": formatted_number,
		"full_name": full_name,
		"pad_length": pad_len,
	}


def get_category_prefix(asset_category):
	"""Fetch configured prefix from Asset Category, cleaned and uppercase."""
	if not asset_category:
		return ""

	val = frappe.db.get_value(
		"Asset Category",
		asset_category,
		["custom_series_prefix", "custom_asset_series"],
		as_dict=True,
	)
	if not val:
		return ""

	prefix = (val.get("custom_series_prefix") or "").strip().upper()
	if not prefix and val.get("custom_asset_series"):
		# e.g. "AHT-LAP-AMD-.###" or "LAP-.####" -> extract "AHT-LAP-AMD" or "LAP"
		series_line = val["custom_asset_series"].strip().splitlines()[0].strip()
		prefix = re.sub(r"-\.?#+$", "", series_line).strip().upper()

	return prefix


def get_highest_asset_number_and_padding(prefix, asset_category=None):
	"""
	Scans existing assets to find the highest sequential number used with this prefix,
	and determines the minimum digit padding length (default 3, e.g. '001', '046').
	"""
	numbers = []
	pad_lengths = []

	# Match prefix e.g. "AHT-LAP-AMD-%"
	pattern = f"{prefix}-%"
	filters = ["name LIKE %s"]
	params = [pattern]
	if asset_category:
		filters.append("asset_category = %s")
		params.append(asset_category)

	query = f"""
		SELECT name, custom_series_number, custom_device_id
		FROM `tabAsset`
		WHERE {" OR ".join(filters)}
	"""
	try:
		existing_assets = frappe.db.sql(query, tuple(params), as_dict=True)
	except Exception:
		existing_assets = []

	prefix_regex = re.compile(rf"^{re.escape(prefix)}-0*(\d+)$", re.IGNORECASE)

	for row in existing_assets:
		name = row.get("name") or ""
		m = prefix_regex.match(name)
		if m:
			raw_suffix = name[len(prefix) + 1 :]
			numbers.append(int(m.group(1)))
			pad_lengths.append(len(raw_suffix))

		csn = str(row.get("custom_series_number") or "").strip()
		if csn.isdigit():
			numbers.append(int(csn))
			pad_lengths.append(len(csn))

		cdi = row.get("custom_device_id")
		if cdi and str(cdi).isdigit():
			numbers.append(int(cdi))

	highest_num = max(numbers) if numbers else 0
	# Default padding is at least 3 digits (e.g. "001", "046"), or whatever max padding was seen (e.g. 4 for LAP-0001)
	pad_len = max(3, max(pad_lengths)) if pad_lengths else 3

	return highest_num, pad_len


def build_full_asset_name(asset_category, series_number):
	"""
	Combines category prefix with user-specified or auto-generated series number.
	Example: AHT-LAP-AMD + 046 -> AHT-LAP-AMD-046
	"""
	prefix = get_category_prefix(asset_category)
	if not prefix:
		return str(series_number).strip()

	num_str = str(series_number).strip()
	if num_str.isdigit():
		num_str = num_str.zfill(max(3, len(num_str)))

	return f"{prefix}-{num_str}"
