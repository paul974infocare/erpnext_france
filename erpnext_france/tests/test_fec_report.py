import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe


fec_report = importlib.import_module(
	"erpnext_france.erpnext_france.report.fichier_des_ecritures_comptables_[fec]."
	"fichier_des_ecritures_comptables_[fec]"
)


class TestFECReport(unittest.TestCase):
	def get_purchase_invoice_result(self, bill_date, against_voucher=None, is_opening=None):
		account = frappe._dict(
			{
				"name": "706 - Prestations de services - TEST",
				"account_number": "706",
				"account_name": "Prestations de services",
			}
		)
		entry = frappe._dict(
			{
				"account": account.name,
				"debit": 100,
				"credit": 0,
				"voucher_no": "PI-0001",
				"voucher_type": "Purchase Invoice",
				"GlPostDate": "2026-02-03",
				"PurPostDate": "2026-02-03",
				"PurBillDate": bill_date,
				"against_voucher": against_voucher,
				"is_opening": is_opening,
			}
		)

		with (
			patch.object(fec_report, "get_gl_entries", return_value=[entry]),
			patch.object(fec_report.frappe, "get_cached_value", return_value="EUR"),
			patch.object(fec_report.frappe.db, "get_value", return_value=0),
			patch.object(fec_report.frappe, "get_all", return_value=[account]),
			patch.object(fec_report, "get_accounting_journals", return_value={"by_name": {}, "by_code": {}}),
		):
			return fec_report.get_result("My Company", "2026", "2026-01-01", "2026-12-31", False)

	def test_purchase_invoice_piece_date_uses_bill_date(self):
		result = self.get_purchase_invoice_result("2026-01-15")

		self.assertEqual(result[0][9], "20260115")

	def test_purchase_invoice_piece_date_falls_back_to_posting_date(self):
		result = self.get_purchase_invoice_result(None)

		self.assertEqual(result[0][9], "20260203")

	def test_purchase_invoice_without_title_falls_back_to_voucher_type(self):
		result = self.get_purchase_invoice_result(None)

		self.assertEqual(result[0][10], "Purchase Invoice")
		self.assertTrue(result[0][10])

	def test_lettrage_fields_stay_empty_with_against_voucher(self):
		result = self.get_purchase_invoice_result(None, against_voucher="SI-0001")

		self.assertEqual(result[0][13:15], ["", ""])

	def test_opening_entry_uses_opening_entry_journal_as_entry_label(self):
		result = self.get_purchase_invoice_result(None, is_opening="Yes")

		self.assertEqual(result[0][10], "Opening Entry Journal")

	@patch.object(fec_report, "format_datetime", return_value="20260101")
	@patch.object(fec_report, "get_accounting_journals", return_value={"by_name": {}, "by_code": {}})
	@patch.object(fec_report.frappe.db, "get_value", return_value=0)
	@patch.object(fec_report.frappe, "get_cached_value", return_value="EUR")
	@patch.object(fec_report, "get_gl_entries")
	@patch.object(fec_report.frappe, "get_all")
	def test_compte_lib_uses_account_name(
		self, get_all, get_gl_entries, get_cached_value, get_value, get_accounting_journals, format_datetime
	):
		get_all.return_value = [
			frappe._dict(
				{
					"name": "706 - Prestations de services - TEST",
					"account_number": "706",
					"account_name": "Prestations de services",
				}
			)
		]
		get_gl_entries.return_value = [
			frappe._dict(
				{
					"account": "706 - Prestations de services - TEST",
					"debit": 100,
					"credit": 0,
					"voucher_no": "JV-0001",
					"voucher_type": "Journal Entry",
				}
			)
		]

		result = fec_report.get_result("My Company", "2026", "2026-01-01", "2026-12-31", False)

		self.assertEqual(result[0][4:6], ["706", "Prestations de services"])

	def test_standard_fec_export_orders_entries_by_aen(self):
		entries = [
			{"voucher_no": "JV-0001", "posting_date": "2026-01-15", "accounting_entry_number": "000003"},
			{"voucher_no": "SI-0001", "posting_date": "2026-01-15", "accounting_entry_number": "000001"},
			{"voucher_no": "JV-0001", "posting_date": "2026-01-15", "accounting_entry_number": "000004"},
		]

		class RecordingQuery:
			def __init__(self):
				self.ordering = []

			def orderby(self, field, order=None):
				self.ordering.append((field, order))
				return self

			def groupby(self, *fields):
				return self

		query = RecordingQuery()
		gle = SimpleNamespace(
			accounting_entry_number="accounting_entry_number",
			name="name",
			posting_date="posting_date",
			voucher_no="voucher_no",
		)

		fec_report.get_fec_query_order(query, gle, "Standard FEC Export")

		self.assertEqual(
			[entry["accounting_entry_number"] for entry in sorted(entries, key=lambda entry: entry["accounting_entry_number"])],
			["000001", "000003", "000004"],
		)
		self.assertEqual(query.ordering, [(gle.accounting_entry_number, fec_report.Order.asc), (gle.name, fec_report.Order.asc)])

	@patch.object(fec_report.frappe, "get_all")
	def test_accounting_journal_is_resolved_by_name_for_exported_company(self, get_all):
		get_all.return_value = [
			{
				"name": "Accounting Journal 0001",
				"journal_code": "VE",
				"journal_name": "Ventes",
			}
		]

		journals = fec_report.get_accounting_journals("My Company")

		get_all.assert_called_once_with(
			"Accounting Journal",
			filters={"company": "My Company"},
			fields=["name", "journal_code", "journal_name"],
		)
		self.assertEqual(
			fec_report.get_journal_values(
				{"accounting_journal": "Accounting Journal 0001", "voucher_no": "VE-0001"},
				journals,
			),
			("VE", "Ventes"),
		)

	@patch.object(fec_report.frappe, "get_all")
	def test_accounting_journal_from_another_company_is_not_resolved(self, get_all):
		get_all.return_value = []

		journals = fec_report.get_accounting_journals("My Company")

		self.assertEqual(
			fec_report.get_journal_values(
				{"accounting_journal": "Other Company Journal", "voucher_no": "VE-0001"},
				journals,
			),
			("", ""),
		)

	def test_voucher_number_fallback_is_kept_without_accounting_journal(self):
		self.assertEqual(
			fec_report.get_journal_values(
				{"voucher_no": "VE-0001"},
				{"by_name": {}, "by_code": {"VE": "Ventes"}},
			),
			("VE", "Ventes"),
		)

	def test_company_currency_is_not_exported_as_transaction_currency(self):
		amount, currency = fec_report.get_transaction_currency_values(
			{
				"transaction_currency": "EUR",
				"account_currency": "USD",
				"debitTransactionCurr": 100,
				"creditTransactionCurr": 0,
			},
			"EUR",
		)

		self.assertEqual((amount, currency), ("", ""))

	def test_foreign_debit_uses_transaction_currency_amount(self):
		amount, currency = fec_report.get_transaction_currency_values(
			{
				"transaction_currency": "USD",
				"account_currency": "EUR",
				"debitTransactionCurr": 125.5,
				"creditTransactionCurr": 0,
			},
			"EUR",
		)

		self.assertEqual((amount, currency), ("125,50", "USD"))

	def test_foreign_credit_is_signed_negative(self):
		amount, currency = fec_report.get_transaction_currency_values(
			{
				"transaction_currency": "USD",
				"account_currency": "EUR",
				"debitTransactionCurr": 0,
				"creditTransactionCurr": 87.25,
			},
			"EUR",
		)

		self.assertEqual((amount, currency), ("-87,25", "USD"))

	def test_transaction_currency_mapping_is_independent_of_account_currency(self):
		amount, currency = fec_report.get_transaction_currency_values(
			{
				"transaction_currency": "USD",
				"account_currency": "USD",
				"debitTransactionCurr": 42,
				"creditTransactionCurr": 0,
			},
			"EUR",
		)

		self.assertEqual((amount, currency), ("42,00", "USD"))


if __name__ == "__main__":
	unittest.main()