import copy
import unittest
from unittest.mock import patch

import frappe

from erpnext_france.utils.repost_accounting_ledger import (
	_get_gl_fieldnames,
	_gl_substance,
	_repost_changes_accounting,
	validate_repost_accounting_ledger,
)


class TestRepostAccountingLedger(unittest.TestCase):
	def make_document(self, company, delete_cancelled_entries):
		return frappe._dict(
			{
				"company": company,
				"delete_cancelled_entries": delete_cancelled_entries,
			}
		)

	def make_gl_entry(self, **values):
		entry = {
			"account": "Sales - FC",
			"voucher_type": "Sales Invoice",
			"voucher_no": "ACC-SINV-2026-00007",
			"posting_date": "2026-09-16",
			"account_currency": "EUR",
			"party_type": "Customer",
			"party": "Customer A",
			"cost_center": "Main - FC",
			"region": "North",
			"debit": 0,
			"credit": 100,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": 100,
		}
		entry.update(values)
		return frappe._dict(entry)

	def make_inverse(self, entry, posting_date="2026-09-29"):
		inverse = copy.deepcopy(entry)
		inverse.posting_date = posting_date
		for debit_field, credit_field in (
			("debit", "credit"),
			("debit_in_account_currency", "credit_in_account_currency"),
			("debit_in_transaction_currency", "credit_in_transaction_currency"),
		):
			if debit_field in entry or credit_field in entry:
				inverse[debit_field], inverse[credit_field] = entry.get(credit_field, 0), entry.get(debit_field, 0)
		return inverse

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
		with (
			patch.object(frappe.db, "get_value", return_value="France") as get_value,
			patch("erpnext_france.utils.repost_accounting_ledger.is_immutable_ledger_enabled", return_value=False),
		):
			validate_repost_accounting_ledger(doc)

		get_value.assert_called_once_with("Company", "French Company", "country")

	def test_allows_destructive_repost_outside_supported_company_scope(self):
		doc = self.make_document("Other Company", 1)
		with patch.object(frappe.db, "get_value", return_value="Germany"):
			validate_repost_accounting_ledger(doc)

	def test_uses_explicit_gl_substance_allowlist(self):
		active = [
			frappe._dict(
				{
					"name": "GL-1",
					"creation": "2026-01-01 10:00:00",
					"modified": "2026-01-01 10:00:00",
					"accounting_entry_number": "AEN-1",
					"account": "Cash - FC",
					"voucher_no": "JE-1",
					"remarks": "Journal label",
					"debit": 100,
					"credit": 0,
				}
			)
		]
		expected = [
			frappe._dict(
				{
					"name": "GL-2",
					"creation": "2026-01-01 11:00:00",
					"modified": "2026-01-01 11:00:00",
					"accounting_entry_number": "AEN-2",
					"account": "Cash - FC",
					"voucher_no": "JE-1",
					"remarks": "Journal label",
					"debit": 100,
					"credit": 0,
				}
			)
		]

		fieldnames = _get_gl_fieldnames(active, expected)
		self.assertEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))
		self.assertNotIn("name", fieldnames)
		self.assertNotIn("accounting_entry_number", fieldnames)
		self.assertNotIn("remarks", fieldnames)

		expected[0].debit = 125
		self.assertNotEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))

		expected[0].debit = 100
		expected[0].remarks = "Different FEC label"
		self.assertEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))

	def test_non_monetary_empty_values_match_missing_values(self):
		for fieldname in ("finance_book", "transaction_date", "against_voucher", "against_voucher_type"):
			with self.subTest(fieldname=fieldname):
				active = [self.make_gl_entry(**{fieldname: ""})]
				expected = [self.make_gl_entry()]
				fieldnames = _get_gl_fieldnames(active, expected)
				self.assertEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))

				active[0][fieldname] = None
				self.assertEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))

				active[0][fieldname] = "Non-empty value"
				self.assertNotEqual(_gl_substance(active, fieldnames), _gl_substance(expected, fieldnames))

	@patch("erpnext_france.utils.repost_accounting_ledger.get_accounting_dimensions", return_value=["region"])
	def test_empty_ledger_equal_to_expected_is_noop(self, dimensions):
		doc = frappe._dict({"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00007"})
		with (
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
				return_value=[],
			),
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
				return_value=[],
			),
		):
			self.assertFalse(_repost_changes_accounting(doc))

	@patch("erpnext_france.utils.repost_accounting_ledger.get_accounting_dimensions", return_value=["region"])
	def test_reduces_one_repost_cycle_for_all_supported_vouchers(self, dimensions):
		voucher_entries = {
			"Sales Invoice": {},
			"Purchase Invoice": {"account": "Expense - FC", "party_type": "Supplier", "party": "Supplier A"},
			"Purchase Receipt": {"account": "Stock - FC", "voucher_detail_no": "PR-ITEM-1"},
			"Payment Entry": {"account": "Bank - FC", "against_voucher_type": "Sales Invoice", "against_voucher": "SI-1"},
			"Journal Entry": {"account": "Expense - FC", "against": "Cash - FC"},
		}
		for voucher_type, fields in voucher_entries.items():
			with self.subTest(voucher_type=voucher_type):
				expected = self.make_gl_entry(voucher_type=voucher_type, **fields)
			inverse = self.make_inverse(expected)
			with (
				patch(
					"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
					return_value=[expected, inverse, copy.deepcopy(expected)],
				),
				patch(
					"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
					return_value=[expected],
				),
			):
				doc = frappe._dict({"doctype": voucher_type, "name": expected.voucher_no})
				self.assertFalse(_repost_changes_accounting(doc))

	@patch("erpnext_france.utils.repost_accounting_ledger.get_accounting_dimensions", return_value=["region"])
	def test_reduces_multiple_repost_cycles_and_detects_changed_final_generation(self, dimensions):
		original = self.make_gl_entry()
		first_inverse = self.make_inverse(original)
		first_regeneration = copy.deepcopy(original)
		second_inverse = self.make_inverse(first_regeneration, posting_date="2026-09-30")
		final_regeneration = copy.deepcopy(original)
		final_regeneration.credit = 125
		final_regeneration.credit_in_account_currency = 125
		final_inverse = self.make_inverse(final_regeneration, posting_date="2026-10-01")
		doc = frappe._dict({"doctype": "Sales Invoice", "name": original.voucher_no})

		with (
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
				return_value=[original, first_inverse, first_regeneration, second_inverse, final_regeneration, final_inverse],
			),
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
				return_value=[original],
			),
		):
			self.assertTrue(_repost_changes_accounting(doc))

		with (
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
				return_value=[original, first_inverse, first_regeneration, second_inverse, copy.deepcopy(original)],
			),
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
				return_value=[original],
			),
		):
			self.assertFalse(_repost_changes_accounting(doc))

	@patch("erpnext_france.utils.repost_accounting_ledger.get_accounting_dimensions", return_value=["region"])
	def test_runtime_noop_ignores_persisted_gl_enrichments(self, dimensions):
		active = [
			frappe._dict(
				{
					"account": "Sales - FC",
					"voucher_type": "Sales Invoice",
					"voucher_no": "ACC-SINV-2026-00007",
					"posting_date": "2026-01-15",
					"account_currency": "EUR",
					"party_type": "Customer",
					"party": "Customer A",
					"cost_center": "Main - FC",
					"region": "North",
					"debit": 0,
					"credit": 100,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": 100,
					"remarks": "Enriched persisted label",
					"debit_in_reporting_currency": 0,
					"credit_in_reporting_currency": 100,
					"reporting_currency_exchange_rate": 1,
					"is_advance": "No",
				}
			)
		]
		expected = [
			frappe._dict(
				{
					"account": "Sales - FC",
					"voucher_type": "Sales Invoice",
					"voucher_no": "ACC-SINV-2026-00007",
					"posting_date": "2026-01-15",
					"account_currency": "EUR",
					"party_type": "Customer",
					"party": "Customer A",
					"cost_center": "Main - FC",
					"region": "North",
					"debit": 0,
					"credit": 100,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": 100,
				}
			)
		]
		doc = frappe._dict({"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00007"})

		with (
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
				return_value=active,
			),
			patch(
				"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
				return_value=expected,
			),
		):
			self.assertFalse(_repost_changes_accounting(doc))

	@patch("erpnext_france.utils.repost_accounting_ledger.get_accounting_dimensions", return_value=["region"])
	def test_detects_each_accounting_substance_difference(self, dimensions):
		base = {
			"account": "Sales - FC",
			"voucher_type": "Sales Invoice",
			"voucher_no": "ACC-SINV-2026-00007",
			"posting_date": "2026-01-15",
			"account_currency": "EUR",
			"party_type": "Customer",
			"party": "Customer A",
			"cost_center": "Main - FC",
			"region": "North",
			"debit": 0,
			"credit": 100,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": 100,
		}
		doc = frappe._dict({"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00007"})

		for fieldname, value in {
			"account": "Other Income - FC",
			"credit": 125,
			"party": "Customer B",
			"posting_date": "2026-01-16",
			"account_currency": "USD",
			"cost_center": "Other - FC",
			"region": "South",
		}.items():
			with self.subTest(fieldname=fieldname):
				active = [frappe._dict(copy.deepcopy(base))]
				expected = [frappe._dict(copy.deepcopy(base))]
				expected[0][fieldname] = value
				with (
					patch(
						"erpnext_france.utils.repost_accounting_ledger._get_active_gl_entries",
						return_value=active,
					),
					patch(
						"erpnext_france.utils.repost_accounting_ledger._get_expected_gl_entries",
						return_value=expected,
					),
				):
					self.assertTrue(_repost_changes_accounting(doc))

	@patch("erpnext_france.utils.repost_accounting_ledger.is_immutable_ledger_enabled", return_value=True)
	@patch("erpnext_france.utils.repost_accounting_ledger._repost_changes_accounting", return_value=False)
	def test_blocks_identical_repost_before_generation(self, changes, immutable):
		doc = self.make_document("French Company", 0)
		doc.vouchers = [frappe._dict({"voucher_type": "Journal Entry", "voucher_no": "JE-1"})]

		with (
			patch.object(frappe.db, "get_value", return_value="France"),
			patch.object(frappe, "get_doc", return_value=frappe._dict()),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "would not change"):
				validate_repost_accounting_ledger(doc)

		changes.assert_called_once()
		immutable.assert_called_once()

	@patch("erpnext_france.utils.repost_accounting_ledger.is_immutable_ledger_enabled", return_value=True)
	@patch("erpnext_france.utils.repost_accounting_ledger._repost_changes_accounting", return_value=True)
	def test_allows_changed_repost(self, changes, immutable):
		doc = self.make_document("French Company", 0)
		doc.vouchers = [frappe._dict({"voucher_type": "Journal Entry", "voucher_no": "JE-1"})]

		with (
			patch.object(frappe.db, "get_value", return_value="France"),
			patch.object(frappe, "get_doc", return_value=frappe._dict()),
		):
			validate_repost_accounting_ledger(doc)

		changes.assert_called_once()
		immutable.assert_called_once()

	@patch("erpnext_france.utils.repost_accounting_ledger.is_immutable_ledger_enabled", return_value=True)
	def test_does_not_compare_outside_supported_company_scope(self, immutable):
		doc = self.make_document("Other Company", 0)
		doc.vouchers = [frappe._dict({"voucher_type": "Journal Entry", "voucher_no": "JE-1"})]

		with (
			patch.object(frappe.db, "get_value", return_value="Germany"),
			patch("erpnext_france.utils.repost_accounting_ledger._repost_changes_accounting") as changes,
		):
			validate_repost_accounting_ledger(doc)

		changes.assert_not_called()
		immutable.assert_not_called()


if __name__ == "__main__":
	unittest.main()