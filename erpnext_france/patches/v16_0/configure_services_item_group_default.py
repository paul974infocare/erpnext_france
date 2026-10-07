import frappe

from erpnext_france.setup import (
	SUPPORTED_ACCOUNTING_COUNTRIES,
	configure_french_company_defaults,
)


def execute():
	companies = frappe.get_all(
		"Company",
		filters={"country": ["in", SUPPORTED_ACCOUNTING_COUNTRIES]},
		fields=["name", "country"],
	)

	for company in companies:
		configure_french_company_defaults(company)
