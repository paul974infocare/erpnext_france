from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.controllers.party import (
	_get_party_details,
	get_due_date,
	get_due_date_from_template_france,
	get_party_details,
)


class TestPartyCompatibility(FrappeTestCase):
	def test_get_party_details_accepts_and_forwards_dispatch_address(self):
		with (
			patch(
				"erpnext_france.controllers.party.frappe.db.exists",
				return_value=True,
			),
			patch(
				"erpnext_france.controllers.party._get_party_details",
				return_value={},
			) as mocked_get_party_details,
		):
			get_party_details(
				party="_Test Supplier",
				party_type="Supplier",
				company="_Test Company",
				doctype="Purchase Invoice",
				dispatch_address="_Test Dispatch Address",
			)

		self.assertEqual(
			mocked_get_party_details.call_args.args[14],
			"_Test Dispatch Address",
		)

	def test_private_party_details_forwards_dispatch_address_to_erpnext(self):
		supplier = frappe._dict(
			{
				"name": "_Test Supplier",
				"default_currency": "EUR",
				"supplier_group": "_Test Supplier Group",
			}
		)

		with (
			patch(
				"erpnext_france.controllers.party.set_account_and_due_date",
				return_value={"supplier": "_Test Supplier"},
			),
			patch(
				"erpnext_france.controllers.party.frappe.get_doc",
				return_value=supplier,
			),
			patch(
				"erpnext_france.controllers.party.set_address_details",
				return_value=(None, None),
			) as mocked_set_address_details,
			patch("erpnext_france.controllers.party.set_contact_details"),
			patch("erpnext_france.controllers.party.set_other_values"),
			patch("erpnext_france.controllers.party.set_price_list"),
			patch(
				"erpnext_france.controllers.party.set_taxes",
				return_value=None,
			),
			patch(
				"erpnext_france.controllers.party.frappe.get_value",
				return_value=None,
			),
		):
			_get_party_details(
				party="_Test Supplier",
				party_type="Supplier",
				company="_Test Company",
				doctype="Purchase Invoice",
				ignore_permissions=True,
				fetch_payment_terms_template=False,
				dispatch_address="_Test Dispatch Address",
			)

		self.assertEqual(
			mocked_set_address_details.call_args.args[8],
			"_Test Dispatch Address",
		)
		self.assertTrue(mocked_set_address_details.call_args.kwargs["ignore_permissions"])

	def test_mixed_payment_terms_template_preserves_erpnext_cumulative_semantics(self):
		template = frappe._dict(
			{
				"terms": [
					frappe._dict(
						{
							"payment_term": "_France 30 EOM",
							"credit_days": 30,
							"credit_months": 0,
							"due_date_based_on": "Day(s) after invoice date",
						}
					),
					frappe._dict(
						{
							"payment_term": "_Standard 90",
							"credit_days": 90,
							"credit_months": 0,
							"due_date_based_on": "Day(s) after invoice date",
						}
					),
				]
			}
		)

		payment_terms = {
			"_France 30 EOM": frappe._dict(
				{
					"custom_due_date_based_on_france": "Day(s) after invoice date, end of month",
					"custom_end_of_month_day": 0,
				}
			),
			"_Standard 90": frappe._dict(
				{
					"custom_due_date_based_on_france": None,
					"custom_end_of_month_day": 0,
				}
			),
		}

		def get_doc(doctype, name):
			if doctype == "Payment Terms Template":
				return template

			if doctype == "Payment Term":
				return payment_terms[name]

			raise AssertionError(f"Unexpected document: {doctype} {name}")

		with patch(
			"erpnext_france.controllers.party.frappe.get_doc",
			side_effect=get_doc,
		):
			due_date = get_due_date_from_template_france(
				"_Mixed Template",
				"2026-09-10",
				None,
			)

		self.assertEqual(str(due_date), "2027-01-29")

	def test_standard_payment_terms_template_matches_erpnext(self):
		from erpnext.accounts.party import get_due_date_from_template

		template = frappe._dict(
			{
				"terms": [
					frappe._dict(
						{
							"payment_term": "_Standard 30",
							"credit_days": 30,
							"credit_months": 0,
							"due_date_based_on": "Day(s) after invoice date",
						}
					),
					frappe._dict(
						{
							"payment_term": "_Standard 90",
							"credit_days": 90,
							"credit_months": 0,
							"due_date_based_on": "Day(s) after invoice date",
						}
					),
				]
			}
		)

		payment_term = frappe._dict(
			{
				"custom_due_date_based_on_france": None,
				"custom_end_of_month_day": 0,
			}
		)

		def get_doc(doctype, name):
			if doctype == "Payment Terms Template":
				return template

			if doctype == "Payment Term":
				return payment_term

			raise AssertionError(f"Unexpected document: {doctype} {name}")

		with patch(
			"erpnext_france.controllers.party.frappe.get_doc",
			side_effect=get_doc,
		), patch(
			"erpnext.accounts.party.frappe.get_doc",
			side_effect=get_doc,
		):
			france_due_date = get_due_date_from_template_france(
				"_Standard Template",
				"2026-09-10",
				None,
			)
			erpnext_due_date = get_due_date_from_template(
				"_Standard Template",
				"2026-09-10",
				None,
			)

		self.assertEqual(france_due_date, erpnext_due_date)

	def test_get_due_date_forwards_company_to_payment_terms_template(self):
		with patch(
			"erpnext_france.controllers.party.get_payment_terms_template",
			return_value=None,
		) as mocked_get_payment_terms_template:
			get_due_date(
				posting_date="2026-09-10",
				party_type="Customer",
				party="_Test Customer",
				company="_Test Company",
			)

		mocked_get_payment_terms_template.assert_called_once_with(
			"_Test Customer",
			"Customer",
			doctype=None,
			company="_Test Company",
		)
