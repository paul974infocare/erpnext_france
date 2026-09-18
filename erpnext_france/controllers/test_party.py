from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.controllers.party import _get_party_details, get_party_details


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
