import frappe

from erpnext_france.setup import SUPPORTED_ACCOUNTING_COUNTRIES, set_french_accounting_settings


def execute():
	companies = frappe.get_all(
		"Company",
		filters={"country": ["in", SUPPORTED_ACCOUNTING_COUNTRIES]},
		fields=["name"],
		limit=1,
	)

	if companies:
		set_french_accounting_settings()