__version__ = "0.0.1"

import frappe
import frappe.translate

if not hasattr(frappe.translate, "load_all_translations"):

	@frappe.whitelist(allow_guest=True)
	def load_all_translations(lang=None, hash=None, app=None):
		return frappe.translate.get_all_translations(lang or getattr(frappe.local, "lang", "en") or "en")

	frappe.translate.load_all_translations = load_all_translations
