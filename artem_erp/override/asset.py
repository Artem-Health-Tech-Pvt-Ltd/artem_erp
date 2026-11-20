# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from erpnext.assets.doctype.asset.asset import Asset
from frappe.model.naming import make_autoname


class CustomAsset(Asset):
	"""Extends the standard ERPNext Asset with:
	- Category-driven auto-naming  (LAP-0001, DESK-0002 …)
	- Auto device_id from the numeric suffix
	- Defaults: is_existing_asset=1, calculate_depreciation=0
	- Warranty auto-calculation
	"""

	def autoname(self):
		"""Override naming: combine category prefix with user-specified or next sequential number."""
		from artem_erp.artem_erp.doctype.asset_category_specification.asset_category_specification import (
			build_full_asset_name,
			get_category_prefix,
			get_next_asset_number,
		)

		if self.asset_category:
			prefix = get_category_prefix(self.asset_category)
			if prefix:
				# Use user-entered custom_series_number or fetch next available
				num_val = getattr(self, "custom_series_number", None)
				if num_val and str(num_val).strip():
					num_str = str(num_val).strip()
					if num_str.isdigit():
						num_str = num_str.zfill(max(3, len(num_str)))
					self.custom_series_number = num_str
				else:
					next_info = get_next_asset_number(self.asset_category)
					self.custom_series_number = next_info.get("next_number")

				candidate_name = build_full_asset_name(self.asset_category, self.custom_series_number)

				# Check uniqueness
				if frappe.db.exists("Asset", candidate_name):
					frappe.throw(
						frappe._(
							"Asset with ID '{0}' already exists. Please choose a different Series Number."
						).format(candidate_name),
						title=frappe._("Duplicate Asset ID"),
					)

				self.name = candidate_name
				if str(self.custom_series_number).isdigit():
					self.custom_device_id = int(self.custom_series_number)
				return

		# Fallback to standard naming if no category series is configured
		super().autoname()

	def before_insert(self):
		"""Set defaults and derive device_id before record hits the DB."""
		# Existing Asset removes standard Purchase Receipt / Invoice requirements
		self.asset_type = "Existing Asset"
		self.is_existing_asset = 1
		self.calculate_depreciation = 0

		# Ensure purchase_date is populated so standard ERPNext validations pass
		if not getattr(self, "purchase_date", None):
			self.purchase_date = self.custom_warranty_start or frappe.utils.nowdate()

		# Auto-fill item_code from category's linked item (if blank)
		if self.asset_category and not self.item_code:
			default_item = frappe.db.get_value(
				"Asset Category",
				self.asset_category,
				"custom_default_item",
			)
			if default_item:
				self.item_code = default_item

		# item_name keeps in sync with item_code
		if self.item_code and not self.item_name:
			self.item_name = frappe.db.get_value("Item", self.item_code, "item_name") or self.item_code

		# Ensure asset_name is set
		if not self.asset_name:
			self.asset_name = self.item_name or self.name or self.asset_category

		# Populate specifications table if not already filled
		if not self.get("custom_specifications"):
			self._load_specifications_from_category()

		# Sync custodian employee details and status
		self._sync_custodian_and_status()

	def validate(self):
		"""Extended validation: specs, types, warranty dates, price."""
		self.asset_type = "Existing Asset"
		self.is_existing_asset = 1
		self.calculate_depreciation = 0

		if not getattr(self, "purchase_date", None):
			self.purchase_date = self.custom_warranty_start or frappe.utils.nowdate()

		if not self.asset_name:
			self.asset_name = self.name or self.item_name or self.asset_category

		# Set device_id and custom_series_number from the numeric suffix of the name
		if self.name:
			try:
				suffix = self.name.rsplit("-", 1)[-1]
				if suffix.isdigit():
					if not getattr(self, "custom_series_number", None):
						self.custom_series_number = suffix
					self.custom_device_id = int(suffix)
			except ValueError, AttributeError:
				pass

		# Rebuild spec rows if category template changed (API edits)
		self._sync_spec_rows()

		# Validate mandatory spec values
		self._validate_spec_values()

		# Validate spec value types
		self._validate_spec_types()

		# Warranty dates
		if self.custom_warranty_start and self.custom_warranty_expiry:
			ws = frappe.utils.getdate(self.custom_warranty_start)
			we = frappe.utils.getdate(self.custom_warranty_expiry)
			if we < ws:
				frappe.throw(
					frappe._("Warranty Expiry cannot be before Warranty Start."),
					title=frappe._("Invalid Warranty Dates"),
				)

		# Maintenance summary calculation
		self._calculate_maintenance_summary()

		# Validate that an asset under repair cannot be assigned to an employee
		self._validate_repair_assignment()

		# Sync custodian employee details and status
		self._sync_custodian_and_status()

		# Call standard validation last
		super().validate()

	def before_update_after_submit(self):
		"""Recalculate maintenance summary when child records are updated after submit."""
		self._calculate_maintenance_summary()
		self._validate_repair_assignment()
		self._sync_custodian_and_status()
		if hasattr(super(), "before_update_after_submit"):
			super().before_update_after_submit()

	def make_asset_movement(self):
		"""Create initial receipt movement bypassing India Compliance GST e-Waybill validations."""
		reference_doctype = (
			"Purchase Receipt" if getattr(self, "purchase_receipt", None) else "Purchase Invoice"
		)
		reference_docname = getattr(self, "purchase_receipt", None) or getattr(self, "purchase_invoice", None)
		transaction_date = frappe.utils.getdate(self.purchase_date or frappe.utils.nowdate())
		if reference_docname:
			posting_date, posting_time = frappe.db.get_value(
				reference_doctype, reference_docname, ["posting_date", "posting_time"]
			) or (None, None)
			if posting_date:
				transaction_date = frappe.utils.get_datetime(f"{posting_date} {posting_time or '00:00:00'}")

		assets = [
			{
				"asset": self.name,
				"asset_name": self.asset_name,
				"target_location": self.location,
				"to_employee": self.custodian,
				"company": self.company,
			}
		]
		asset_movement = frappe.get_doc(
			{
				"doctype": "Asset Movement",
				"assets": assets,
				"purpose": "Receipt",
				"company": self.company,
				"transaction_date": transaction_date,
				"reference_doctype": reference_doctype,
				"reference_name": reference_docname,
			}
		)
		asset_movement.flags.ignore_validate = True
		asset_movement.flags.ignore_mandatory = True
		asset_movement.flags.ignore_permissions = True
		asset_movement.insert()
		asset_movement.flags.ignore_validate = True
		asset_movement.submit()

	def on_submit(self):
		super().on_submit()
		self._sync_custodian_employee()
		self._sync_asset_allocation()

	def on_update(self):
		if hasattr(super(), "on_update"):
			super().on_update()
		self._sync_custodian_employee()
		self._sync_asset_allocation()

	def on_update_after_submit(self):
		if hasattr(super(), "on_update_after_submit"):
			super().on_update_after_submit()
		self._sync_custodian_employee()
		self._sync_asset_allocation()

	def _sync_asset_allocation(self):
		try:
			from artem_erp.artem_erp.doctype.employee_asset_allocation.employee_asset_allocation import (
				sync_assignment_on_asset_save,
			)

			sync_assignment_on_asset_save(self)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Asset Allocation Sync Error")

	def _sync_custodian_employee(self):
		custodians = set()
		if getattr(self, "custodian", None):
			custodians.add(self.custodian)
		if hasattr(self, "get_doc_before_save"):
			prev = self.get_doc_before_save()
			if prev and getattr(prev, "custodian", None):
				custodians.add(prev.custodian)

		for emp_id in custodians:
			if frappe.db.exists("Employee", emp_id):
				try:
					emp = frappe.get_doc("Employee", emp_id)
					from artem_erp.doc_events.employee import sync_employee_assets_table

					sync_employee_assets_table(emp)
					emp.flags.ignore_validate = True
					emp.flags.ignore_mandatory = True
					emp.save(ignore_permissions=True)
				except Exception:
					pass

	# ─────────────────────────────── helpers ────────────────────────────────

	def _get_category_series(self):
		"""Return the naming series string stored on the Asset Category."""
		if not self.asset_category:
			return None
		cat = frappe.db.get_value(
			"Asset Category",
			self.asset_category,
			["custom_asset_series", "custom_series_prefix"],
			as_dict=True,
		)
		if not cat:
			return None
		if cat.get("custom_asset_series"):
			# e.g. "LAP-.####" - take the first line if multiple
			series_str = cat["custom_asset_series"].strip().splitlines()[0].strip()
			return series_str or None
		if cat.get("custom_series_prefix"):
			prefix = cat["custom_series_prefix"].strip().upper()
			return f"{prefix}-.####"
		return None

	def _load_specifications_from_category(self):
		"""Copy spec template rows from Asset Category into this asset."""
		if not self.asset_category:
			return
		cat_doc = frappe.get_doc("Asset Category", self.asset_category)
		specs = cat_doc.get("custom_specifications") or []

		for row in specs:
			self.append(
				"custom_specifications",
				{
					"spec_name": row.get("spec_name") or "",
					"data_type": row.get("data_type") or "Data",
					"options": row.get("options") or "",
					"is_mandatory": 1 if row.get("is_mandatory") else 0,
					"value": row.get("default_value") or "",
				},
			)

	def _sync_spec_rows(self):
		"""
		If the category has changed (e.g. via API) and spec rows no longer match
		the template, rebuild them silently. On the UI the client script handles
		this interactively with a confirmation prompt.
		"""
		if not self.asset_category:
			return
		# Only rebuild when the table is completely empty (not a user-clear)
		if self.get("custom_specifications"):
			return
		self._load_specifications_from_category()

	def _validate_spec_values(self):
		"""Throw if any mandatory spec has an empty value."""
		missing = [
			row.spec_name
			for row in self.get("custom_specifications", [])
			if row.is_mandatory and not (row.value and str(row.value).strip())
		]
		if missing:
			frappe.throw(
				frappe._("Required specifications for Asset Category <b>{0}</b>: {1}").format(
					self.asset_category, ", ".join(f"<b>{m}</b>" for m in missing)
				),
				title=frappe._("Mandatory Specification Missing"),
			)

	def _validate_spec_types(self):
		"""Type-check each filled spec value against its declared data_type."""
		for row in self.get("custom_specifications", []):
			val = str(row.value).strip() if row.value else ""
			if not val:
				continue
			dt = row.data_type or "Data"
			try:
				if dt == "Int":
					int(val)
				elif dt == "Float":
					float(val)
				elif dt == "Date":
					frappe.utils.getdate(val)
				elif dt == "Select":
					valid_opts = [o.strip() for o in (row.options or "").splitlines() if o.strip()]
					if valid_opts and val.lower() not in [o.lower() for o in valid_opts]:
						frappe.throw(
							frappe._("Specification <b>{0}</b>: value '{1}' must be one of: {2}").format(
								row.spec_name, val, ", ".join(valid_opts)
							)
						)
			except ValueError, TypeError:
				frappe.throw(
					frappe._("Specification <b>{0}</b>: value '{1}' is not a valid {2}.").format(
						row.spec_name, val, dt
					)
				)

	def _calculate_maintenance_summary(self):
		"""Recalculate maintenance count and total maintenance cost from child records."""
		records = self.get("custom_maintenance_records") or []
		self.custom_maintenance_count = len(records)
		self.custom_total_maintenance_cost = sum(frappe.utils.flt(row.cost) for row in records)

	def _has_active_repair(self):
		"""Returns True if there is an active repair in Asset Repair or pending repair in child table."""
		# 1. Check standard Asset Repair
		if self.name and not self.is_new():
			if frappe.db.exists(
				"Asset Repair",
				{
					"asset": self.name,
					"repair_status": "Pending",
					"docstatus": ("<", 2),
				},
			):
				return True

		# 2. Check child rows in custom_maintenance_records (only In Progress repairs mark it In Repair)
		for row in self.get("custom_maintenance_records") or []:
			if row.get("repair_required") and row.get("maintenance_status") == "In Progress":
				return True

		return False

	def _validate_repair_assignment(self):
		"""Throws an error if user attempts to assign an asset to a custodian while under repair."""
		if self.custodian and (
			self._has_active_repair() or getattr(self, "custom_asset_status", None) == "In Repair"
		):
			frappe.throw(
				frappe._(
					"Asset <b>{0}</b> is currently <b>In Repair</b> and cannot be assigned to an employee until repair is completed."
				).format(self.name or self.asset_name),
				title=frappe._("Asset Under Repair"),
			)

	def _sync_custodian_and_status(self):
		"""Sync Asset Status and Employee details based on Custodian and In Repair selection."""
		# 1. Sync Employee Details
		if self.custodian:
			emp = frappe.db.get_value(
				"Employee",
				self.custodian,
				["employee_name", "company_email", "personal_email", "prefered_email", "user_id"],
				as_dict=True,
			)
			if emp:
				self.custom_employee_name = emp.get("employee_name") or ""
				self.custom_employee_email = (
					emp.get("company_email")
					or emp.get("personal_email")
					or emp.get("user_id")
					or emp.get("prefered_email")
					or ""
				)
			if not getattr(self, "custom_assignment_date", None):
				self.custom_assignment_date = frappe.utils.nowdate()
		else:
			self.custom_employee_name = ""
			self.custom_employee_email = ""
			self.custom_assignment_date = None

		# 2. Status determination
		has_repair = self._has_active_repair()
		current_status = getattr(self, "custom_asset_status", None)

		if has_repair:
			self.custom_asset_status = "In Repair"
		elif current_status == "In Repair":
			# Manually marked In Repair without specific repair record
			pass
		else:
			# Auto status based on custodian
			self.custom_asset_status = "Assigned" if self.custodian else "In Stock"
