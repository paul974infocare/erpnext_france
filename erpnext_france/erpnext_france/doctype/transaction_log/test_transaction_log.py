# Copyright (c) 2025, Scopen and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.utils.transaction_log import (
	check_deletion_permission,
	create_transaction_log,
)


class TestTransactionLog(FrappeTestCase):
	def make_document(self, company, docstatus=1):
		doc = frappe._dict(
			{
				"doctype": "Sales Invoice",
				"name": f"SI-{company}",
				"company": company,
				"docstatus": docstatus,
			}
		)
		doc.as_dict = lambda: doc.copy()
		return doc

	def test_creates_log_for_supported_regions(self):
		for region in ("France", "Guadeloupe", "Martinique", "Réunion"):
			doc = self.make_document(f"Company {region}")
			with (
				patch(
					"erpnext_france.utils.transaction_log.get_region",
					return_value=region,
				) as get_region,
				patch("erpnext_france.utils.transaction_log.frappe.get_doc") as get_doc,
			):
				create_transaction_log(doc, "on_submit")

			get_region.assert_called_once_with(doc.company)
			get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_does_not_create_log_for_mayotte_or_french_guiana(self):
		for region in ("French Guiana", "Mayotte"):
			doc = self.make_document(f"Company {region}")
			with (
				patch(
					"erpnext_france.utils.transaction_log.get_region",
					return_value=region,
				) as get_region,
				patch("erpnext_france.utils.transaction_log.frappe.get_doc") as get_doc,
			):
				create_transaction_log(doc, "on_submit")

			get_region.assert_called_once_with(doc.company)
			get_doc.assert_not_called()

	def test_requires_document_company_for_region(self):
		doc = self.make_document("Réunion Company")

		def get_region_for_document(company):
			self.assertEqual(company, doc.company)
			return "Réunion"

		with (
			patch(
				"erpnext_france.utils.transaction_log.get_region",
				side_effect=get_region_for_document,
			) as get_region,
			patch("erpnext_france.utils.transaction_log.frappe.get_doc") as get_doc,
		):
			create_transaction_log(doc, "on_submit")

		get_region.assert_called_once_with(doc.company)
		get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_blocks_submitted_documents_in_supported_regions(self):
		for region in ("France", "Guadeloupe", "Martinique", "Réunion"):
			doc = self.make_document(f"Company {region}")
			with (
				patch(
					"erpnext_france.utils.transaction_log.get_region",
					return_value=region,
				),
				patch(
					"erpnext_france.utils.transaction_log.frappe.throw",
					side_effect=frappe.ValidationError,
				),
			):
				with self.assertRaises(frappe.ValidationError):
					check_deletion_permission(doc, "on_trash")

	def test_does_not_block_submitted_documents_in_mayotte_or_french_guiana(self):
		for region in ("French Guiana", "Mayotte"):
			doc = self.make_document(f"Company {region}")
			with (
				patch(
					"erpnext_france.utils.transaction_log.get_region",
					return_value=region,
				),
				patch("erpnext_france.utils.transaction_log.frappe.throw") as throw,
			):
				check_deletion_permission(doc, "on_trash")

			throw.assert_not_called()
