import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
    
    
CUSTOM_FIELDS = {
    "Employee": [
        {
            "fieldname": "custom_aadhaar_number",
            "label": "Aadhaar Number",
            "fieldtype": "Data",
            "insert_after": "provident_fund_account",
            "reqd": 1,
            "length": 12,
            "default": "",
            "unique": 1,
            "system_generated": 0,
        }
    ]
}