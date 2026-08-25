# Date : 24th August 2026

import frappe
from frappe import _
from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError, EmployeeCheckin
from hrms.hr.utils import get_distance_between_coordinates


# Override for the Employee Checkin doctype to validate checkin against multiple assigned shift locations not just the primary one.
class CustomEmployeeCheckin(EmployeeCheckin):
	def validate_distance_from_shift_location(self):
		"""Validate Employee Checkin against all Shift Locations
		assigned through custom_shift_assignment_location table.
		"""

		# 1. Check whether geolocation tracking is enabled
		if not frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking"):
			return

		# 2. GPS coordinates are required
		if self.latitude is None or self.longitude is None:
			frappe.throw(_("Latitude and longitude values are required for checking in."))

		# 3. Find active Shift Assignments
		assignments = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": self.employee,
				"shift_type": self.shift,
				"start_date": ["<=", self.time],
				"docstatus": 1,
				"status": "Active",
			},
			or_filters=[
				["end_date", ">=", self.time],
				["end_date", "is", "not set"],
			],
			pluck="name",
		)

		if not assignments:
			return

		# 4. Check every Shift Assignment
		for assignment_name in assignments:
			assignment = frappe.get_doc("Shift Assignment", assignment_name)

			# 5. Get locations from custom child table
			locations = assignment.get("custom_shift_assignment_location") or []

			if not locations:
				continue

			# 6. Check every assigned location
			for row in locations:
				if not row.shift_location:
					continue

				location = frappe.db.get_value(
					"Shift Location",
					row.shift_location,
					[
						"checkin_radius",
						"latitude",
						"longitude",
					],
					as_dict=True,
				)

				if not location:
					continue

				radius = location.checkin_radius
				latitude = location.latitude
				longitude = location.longitude

				# Skip locations where radius is not configured
				if radius is None or radius <= 0:
					continue

				# Skip locations without coordinates
				if latitude is None or longitude is None:
					continue

				# 7. Calculate distance
				distance = get_distance_between_coordinates(
					latitude,
					longitude,
					self.latitude,
					self.longitude,
				)
				# 8. ANY location within radius = ALLOW
				if distance <= radius:
					return

		# 9. No location matched
		frappe.throw(
			_("You must be within the allowed radius of one of your assigned shift locations to check in."),
			exc=CheckinRadiusExceededError,
		)
