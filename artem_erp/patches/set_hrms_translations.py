import frappe


def execute():
	"""Sets translation overrides for Frappe HR -> Artem HR."""
	translations = [
		("Frappe HR", "Artem HR"),
		("Login to Frappe HR", "Login to Artem HR"),
		("Install Frappe HR", "Install Artem HR"),
	]

	for src, trg in translations:
		name = frappe.db.exists("Translation", {"source_text": src, "language": "en"})
		if not name:
			doc = frappe.get_doc(
				{
					"doctype": "Translation",
					"language": "en",
					"source_text": src,
					"translated_text": trg,
				}
			)
			doc.insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Translation", name, "translated_text", trg, update_modified=False)

	frappe.clear_cache()
