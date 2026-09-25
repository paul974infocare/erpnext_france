# Copyright (c) 2024 SCOPEN
# For license information, please see license.txt


import json
import os

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import (
	from_detailed_data,
	update_regional_tax_settings,
)
from frappe import _


@frappe.whitelist(allow_guest=False)
def create_tax_template(doc: str):
	doc = json.loads(doc)

	company_name = doc.get("company_name")
	country = doc.get("country")
	if not frappe.db.exists("Company", company_name):
		frappe.throw(_("Company {} does not exist yet. Taxes setup aborted.").format(company_name))

	file_path = os.path.join(os.path.dirname(__file__), "..", "data", "country_wise_tax.json")
	with open(file_path) as json_file:
		tax_data = json.load(json_file)

	country_wise_tax = tax_data.get(country)

	if not country_wise_tax:
		return

	from_detailed_data(company_name, country_wise_tax)
	apply_fiscal_metadata(country_wise_tax)
	create_tax_rules(company_name, country_wise_tax)
	update_regional_tax_settings(country, company_name)


def create_tax_rules(company_name: str, country_wise_tax: dict):
	for rule in country_wise_tax.get("tax_rules", []):
		tax_type = rule["tax_type"]
		tax_category = rule["tax_category"]
		tax_template_title = rule["tax_template"]
		template_doctype = f"{tax_type} Taxes and Charges Template"

		templates = frappe.get_all(
			template_doctype,
			filters={"company": company_name, "tax_category": tax_category},
			fields=["name", "title"],
		)
		if len(templates) != 1 or templates[0]["title"] != tax_template_title:
			continue

		tax_rule_filters = {
			"company": company_name,
			"tax_type": tax_type,
			"tax_category": tax_category,
			"sales_tax_template": templates[0]["name"] if tax_type == "Sales" else None,
			"purchase_tax_template": templates[0]["name"] if tax_type == "Purchase" else None,
		}
		if frappe.db.exists("Tax Rule", tax_rule_filters):
			continue

		frappe.get_doc(
			{
				"doctype": "Tax Rule",
				**tax_rule_filters,
				"priority": 1,
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)


def apply_fiscal_metadata(country_wise_tax: dict):
	fiscal_metadata = country_wise_tax.get("france_fiscal_metadata", {})

	for tax_category, metadata in fiscal_metadata.items():
		if not frappe.db.exists("Tax Category", tax_category):
			frappe.throw(
				_("Tax Category {} does not exist. Fiscal metadata setup aborted.").format(
					tax_category
				)
			)

		values = {
			"custom_france_fiscal_legal_reference": metadata.get("legal_reference"),
			"custom_france_fiscal_invoice_mention": metadata.get("invoice_mention"),
		}

		current_values = frappe.db.get_value(
			"Tax Category",
			tax_category,
			list(values),
			as_dict=True,
		)

		if any(current_values.get(field) != value for field, value in values.items()):
			frappe.db.set_value(
				"Tax Category",
				tax_category,
				values,
				update_modified=False,
			)
