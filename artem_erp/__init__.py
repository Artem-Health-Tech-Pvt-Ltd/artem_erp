import frappe
import frappe.translate

__version__ = "0.0.1"

if not hasattr(frappe.translate, "load_all_translations"):

	@frappe.whitelist(allow_guest=False)  # nosemgrep
	def load_all_translations(
		lang: str | None = None,
		hash: str | None = None,
		app: str | None = None,
	):
		return frappe.translate.get_all_translations(lang or getattr(frappe.local, "lang", "en") or "en")

	frappe.translate.load_all_translations = load_all_translations


def _disconnect_india_compliance_from_assets():
	"""
	Disconnects india_compliance from Asset and Asset Movement, and fixes the upstream
	get_round_off_applicable_accounts signature mismatch between ERPNext and India Compliance.
	IT Assets are internal hardware/devices and do not require GST e-Waybills or tax computation.
	"""
	# 1. Patch ERPNext's get_round_off_applicable_accounts to accept variable args
	try:
		import erpnext.controllers.taxes_and_totals as tat
		if hasattr(tat, "get_round_off_applicable_accounts"):
			_orig_round_off = tat.get_round_off_applicable_accounts

			def safe_get_round_off(company, account_list, *args, **kwargs):
				return _orig_round_off(company, account_list)

			tat.get_round_off_applicable_accounts = safe_get_round_off
	except Exception:
		pass

	# 2. Patch India Compliance taxes controller and asset_movement
	try:
		import india_compliance.gst_india.utils.taxes_controller as tc
		if hasattr(tc, "fetch_round_off_accounts"):
			tc.fetch_round_off_accounts = safe_get_round_off

		import india_compliance.gst_india.overrides.asset_movement as am

		def noop_validate(doc, method=None):
			return

		def noop_before_save(doc, method=None):
			return

		am.validate = noop_validate
		am.before_save = noop_before_save
	except Exception:
		pass


_disconnect_india_compliance_from_assets()
