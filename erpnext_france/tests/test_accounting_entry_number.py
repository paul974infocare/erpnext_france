import unittest
from unittest.mock import Mock, patch

import frappe

from erpnext_france.utils import accounting_entry_number


class TestAccountingEntryNumber(unittest.TestCase):
	def make_gl_entry(self, voucher_type, accounting_entry_number, debit=100, credit=0):
		entry = frappe._dict(
			{
				"name": f"{voucher_type}-GL-1",
				"voucher_type": voucher_type,
				"voucher_no": f"{voucher_type}-1",
				"accounting_entry_number": accounting_entry_number,
				"accounting_journal": "",
				"company": "French Company",
				"account": "Cash - FC",
				"against": "Receivable - FC",
				"debit": debit,
				"credit": credit,
				"debit_in_account_currency": debit,
				"credit_in_account_currency": credit,
			}
		)
		entry.precision = Mock(return_value=2)
		entry.save = Mock()
		return entry

	def tearDown(self):
		contexts = getattr(frappe.flags, accounting_entry_number.CANCELLATION_CONTEXT, None)
		if contexts:
			contexts.clear()
			delattr(frappe.flags, accounting_entry_number.CANCELLATION_CONTEXT)
		if getattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT, None) is not None:
			delattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT)

	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=True)
	def test_cancellation_uses_one_new_number_for_all_supported_vouchers(self, is_immutable):
		voucher_types = ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry")

		with (
			patch.object(accounting_entry_number, "get_accounting_number", return_value="AEN-2026-000000002"),
			patch.object(accounting_entry_number, "get_accounting_journal", return_value="Journal"),
		):
			for voucher_type in voucher_types:
				with self.subTest(voucher_type=voucher_type):
					name = f"{voucher_type}-1"
					doc = frappe._dict({"doctype": voucher_type, "name": name})
					accounting_entry_number.prepare_cancellation_accounting_entry_number(doc)

					first = self.make_gl_entry(voucher_type, "AEN-2026-000000001")
					second = self.make_gl_entry(voucher_type, "AEN-2026-000000001")
					accounting_entry_number.add_accounting_entry_number(first, "on_submit")
					accounting_entry_number.add_accounting_entry_number(second, "on_submit")

					self.assertEqual(first.accounting_entry_number, "AEN-2026-000000002")
					self.assertEqual(second.accounting_entry_number, "AEN-2026-000000002")
					self.assertNotEqual(first.accounting_entry_number, "AEN-2026-000000001")
					accounting_entry_number.clear_cancellation_accounting_entry_number(doc)

				is_immutable.assert_called()

	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=False)
	def test_submit_path_keeps_inherited_number_unchanged(self, is_immutable):
		doc = frappe._dict({"doctype": "Sales Invoice", "name": "Sales Invoice-1"})
		accounting_entry_number.prepare_cancellation_accounting_entry_number(doc)
		entry = self.make_gl_entry("Sales Invoice", "AEN-2026-000000001")

		with patch.object(accounting_entry_number, "get_accounting_number") as get_number:
			accounting_entry_number.add_accounting_entry_number(entry, "on_submit")

		self.assertEqual(entry.accounting_entry_number, "AEN-2026-000000001")
		get_number.assert_not_called()
		is_immutable.assert_called_once()

	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=False)
	def test_submit_lines_share_one_new_number(self, is_immutable):
		first = self.make_gl_entry("Sales Invoice", "")
		second = self.make_gl_entry("Sales Invoice", "")

		with (
			patch.object(
				frappe,
				"get_all",
				 side_effect=[[], [frappe._dict(name="Sales Invoice-GL-1", accounting_entry_number="AEN-2026-000000001")]],
			),
			patch.object(accounting_entry_number, "get_accounting_number", return_value="AEN-2026-000000001"),
			patch.object(accounting_entry_number, "get_accounting_journal", return_value="Journal"),
		):
			accounting_entry_number.add_accounting_entry_number(first, "on_submit")
			accounting_entry_number.add_accounting_entry_number(second, "on_submit")

		self.assertEqual(first.accounting_entry_number, "AEN-2026-000000001")
		self.assertEqual(second.accounting_entry_number, "AEN-2026-000000001")
		is_immutable.assert_not_called()

	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=True)
	def test_cancellation_context_is_cleared(self, is_immutable):
		doc = frappe._dict({"doctype": "Journal Entry", "name": "Journal Entry-1"})
		accounting_entry_number.prepare_cancellation_accounting_entry_number(doc)

		self.assertTrue(hasattr(frappe.flags, accounting_entry_number.CANCELLATION_CONTEXT))
		accounting_entry_number.clear_cancellation_accounting_entry_number(doc)
		contexts = getattr(frappe.flags, accounting_entry_number.CANCELLATION_CONTEXT, None) or {}
		self.assertNotIn((doc.doctype, doc.name), contexts)
		is_immutable.assert_called_once()

	@patch.object(accounting_entry_number, "get_accounting_journal", return_value="Journal")
	@patch.object(accounting_entry_number, "get_accounting_number")
	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=True)
	def test_repost_uses_distinct_numbers_for_all_supported_vouchers(
		self, is_immutable, get_number, get_journal
	):
		voucher_types = (
			"Sales Invoice",
			"Purchase Invoice",
			"Purchase Receipt",
			"Payment Entry",
			"Journal Entry",
		)
		get_number.side_effect = [f"AEN-2026-{index:09d}" for index in range(2, 12)]

		for index, voucher_type in enumerate(voucher_types):
			with self.subTest(voucher_type=voucher_type):
				voucher_no = f"{voucher_type}-1"
				repost_doc = frappe._dict(
					{
						"company": "French Company",
						"vouchers": [
							frappe._dict(
								{
									"voucher_type": voucher_type,
									"voucher_no": voucher_no,
									"status": "",
								}
							)
						],
					}
				)
				with (
					patch.object(frappe, "get_doc", return_value=repost_doc),
					patch.object(frappe.db, "get_value", return_value="France"),
					patch.object(
						frappe,
						"get_all",
						return_value=[frappe._dict(debit=100, credit=0), frappe._dict(debit=0, credit=100)],
					),
				):
					accounting_entry_number.prepare_repost_accounting_entry_numbers(
						method=accounting_entry_number.REPOST_METHOD,
						kwargs={"repost_doc_name": f"RAL-{index + 1}"},
					)

				entries = [
					self.make_gl_entry(voucher_type, "AEN-2026-000000001", debit=100, credit=0),
					self.make_gl_entry(voucher_type, "AEN-2026-000000001", debit=0, credit=100),
					self.make_gl_entry(voucher_type, "AEN-2026-000000001", debit=100, credit=0),
					self.make_gl_entry(voucher_type, "AEN-2026-000000001", debit=0, credit=100),
				]
				for entry in entries:
					accounting_entry_number.add_accounting_entry_number(entry, "on_submit")

				self.assertEqual(entries[0].accounting_entry_number, entries[1].accounting_entry_number)
				self.assertEqual(entries[2].accounting_entry_number, entries[3].accounting_entry_number)
				self.assertNotEqual(entries[0].accounting_entry_number, entries[2].accounting_entry_number)
				self.assertNotEqual(entries[0].accounting_entry_number, "AEN-2026-000000001")
				accounting_entry_number.clear_repost_accounting_entry_numbers(
					method=accounting_entry_number.REPOST_METHOD
				)

		self.assertEqual(get_number.call_count, 10)
		self.assertEqual(get_journal.call_count, 20)
		is_immutable.assert_called()

	@patch.object(accounting_entry_number, "is_immutable_ledger_enabled", return_value=True)
	def test_repost_context_is_prepared_only_for_french_immutable_company(self, is_immutable):
		repost_doc = frappe._dict(
			{
				"company": "French Company",
				"vouchers": [
					frappe._dict(
						{
							"voucher_type": "Journal Entry",
							"voucher_no": "Journal Entry-1",
							"status": "",
						}
					)
				],
			}
		)
		with (
			patch.object(frappe, "get_doc", return_value=repost_doc),
			patch.object(frappe.db, "get_value", return_value="France"),
			patch.object(
				frappe,
				"get_all",
				return_value=[frappe._dict({"debit": 100, "credit": 0})],
			),
		):
			accounting_entry_number.prepare_repost_accounting_entry_numbers(
				method=accounting_entry_number.REPOST_METHOD,
				kwargs={"repost_doc_name": "RAL-1"},
			)

		context = getattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT)
		self.assertEqual(context[("Journal Entry", "Journal Entry-1")]["reversal_remaining"], 1)
		accounting_entry_number.clear_repost_accounting_entry_numbers(
			method=accounting_entry_number.REPOST_METHOD
		)
		self.assertIsNone(getattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT, None))
		is_immutable.assert_called_once()

	def test_repost_context_is_cleared_after_failure(self):
		setattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT, {("Journal Entry", "Journal Entry-1"): {}})
		accounting_entry_number.clear_repost_accounting_entry_numbers(
			method=accounting_entry_number.REPOST_METHOD,
			result=None,
		)

		self.assertIsNone(getattr(frappe.flags, accounting_entry_number.REPOST_CONTEXT, None))


if __name__ == "__main__":
	unittest.main()
