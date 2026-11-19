__version__ = "0.0.1"

import frappe
import frappe.translate

if not hasattr(frappe.translate, "load_all_translations"):

	@frappe.whitelist(allow_guest=False)  # nosemgrep
	def load_all_translations(
		lang: str | None = None,
		hash: str | None = None,
		app: str | None = None,
	):
		return frappe.translate.get_all_translations(lang or getattr(frappe.local, "lang", "en") or "en")

	frappe.translate.load_all_translations = load_all_translations
