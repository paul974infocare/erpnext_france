import unittest
from unittest.mock import patch

import frappe

from erpnext_france.utils.repost_accounting_ledger import validate_repost_accounting_ledger


class TestRepostAccountingLedger(unittest.TestCase):
	def make_document(self, company, delete_cancelled_entries):
		return frappe._dict(
			{
				"company": company,
				"delete_cancelled_entries": delete_cancelled_entries,
			}
		)

	def test_blocks_destructive_repost_for_supported_company(self):
		doc = self.make_document("French Company", 1)
		with patch.object(frappe.db, "get_value", return_value="France"):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"Deleting cancelled ledger entries is not permitted",
			):
				validate_repost_accounting_ledger(doc)

	def test_allows_normal_repost_for_supported_company(self):
		doc = self.make_document("French Company", 0)
		with patch.object(frappe.db, "get_value") as get_value:
			validate_repost_accounting_ledger(doc)

		get_value.assert_not_called()

	def test_allows_destructive_repost_outside_supported_company_scope(self):
		doc = self.make_document("Other Company", 1)
		with patch.object(frappe.db, "get_value", return_value="Germany"):
			validate_repost_accounting_ledger(doc)


if __name__ == "__main__":
	unittest.main()