import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestImportVATEntry(FrappeTestCase):
	def setUp(self):
		accounts = frappe.get_all(
			"Account",
			filters={"account_number": ["in", ["4453", "445621", "445685"]], "is_group": 0},
			fields=["name", "company", "account_number"],
		)
		by_company = {}
		for account in accounts:
			by_company.setdefault(account.company, {})[account.account_number] = account.name
		matching_companies = [
			company for company, company_accounts in by_company.items() if len(company_accounts) == 3
		]
		if not matching_companies:
			self.skipTest("Import VAT account fixtures are not available for one company")
		self.company = matching_companies[0]
		self.accounts = by_company[self.company]

	def make_entry(self, taxable_base, tax_rate, deductible_account, purchase_invoice=None, insert=True):
		entry = frappe.get_doc(
			{
				"doctype": "Import VAT Entry",
				"company": self.company,
				"posting_date": today(),
				"import_reference": "TEST-IMPORT-001",
				"taxable_base": taxable_base,
				"tax_rate": tax_rate,
				"import_vat_due_account": self.accounts["4453"],
				"deductible_tax_account": self.accounts[deductible_account],
				"purchase_invoice": purchase_invoice,
				"naming_series": "IM-VAT-.YYYY.-",
			}
		)

		tax = flt(
			flt(taxable_base) * flt(tax_rate) / 100,
			entry.precision("tax_due"),
		)
		entry.tax_due = tax
		entry.deductible_tax = tax

		if insert:
			entry.insert()
		return entry

	def assert_gl_lines(self, journal_entry, debit_account, amount):
		lines = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Journal Entry", "voucher_no": journal_entry},
			fields=["account", "debit", "credit"],
			order_by="account",
		)
		self.assertEqual(len(lines), 2)
		self.assertEqual(
			{line.account: (flt(line.debit, 2), flt(line.credit, 2)) for line in lines},
			{
				debit_account: (amount, 0),
				self.accounts["4453"]: (0, amount),
			},
		)

	def test_85_percent_import_vat(self):
		entry = self.make_entry(100, 8.5, "445685")
		entry.submit()
		self.assertEqual(entry.tax_due, 8.5)
		self.assertEqual(entry.deductible_tax, 8.5)
		self.assert_gl_lines(entry.journal_entry, self.accounts["445685"], 8.5)
		entry.cancel()

	def test_import_base_is_independent_from_purchase_invoice_amount(self):
		purchase_invoice = frappe.db.get_value(
			"Purchase Invoice", {"company": self.company, "grand_total": 100}, "name"
		)
		if not purchase_invoice:
			self.skipTest("No 100 EUR Purchase Invoice fixture is available")

		entry = self.make_entry(120, 8.5, "445685", purchase_invoice)
		entry.submit()
		self.assertEqual(entry.tax_due, 10.2)
		self.assert_gl_lines(entry.journal_entry, self.accounts["445685"], 10.2)
		entry.cancel()

	def test_21_percent_import_vat(self):
		entry = self.make_entry(100, 2.1, "445621")
		entry.submit()
		self.assert_gl_lines(entry.journal_entry, self.accounts["445621"], 2.1)
		entry.cancel()

	def test_one_active_journal_entry_per_import_vat_entry(self):
		entry = self.make_entry(100, 8.5, "445685")
		entry.submit()
		journal_entry = entry.journal_entry
		self.assertEqual(
			frappe.db.count(
				"Journal Entry", {"user_remark": f"Import VAT Entry {entry.name}", "docstatus": 1}
			),
			1,
		)
		self.assertRaises(frappe.ValidationError, entry.validate)
		entry.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", journal_entry, "docstatus"), 2)

	def test_cancellation_uses_native_journal_entry_cancellation(self):
		entry = self.make_entry(100, 8.5, "445685")
		entry.submit()
		journal_entry = entry.journal_entry
		entry.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", journal_entry, "docstatus"), 2)
		self.assertTrue(
			frappe.db.exists(
				"GL Entry", {"voucher_type": "Journal Entry", "voucher_no": journal_entry, "is_cancelled": 1}
			)
		)

	def test_tax_due_is_recalculated_from_base_and_rate(self):
		entry = self.make_entry(120, 8.5, "445685", insert=False)
		entry.tax_due = 999

		entry.validate()

		expected_tax = flt(
			flt(entry.taxable_base) * flt(entry.tax_rate) / 100,
			entry.precision("tax_due"),
		)
		self.assertEqual(entry.tax_due, expected_tax)

	def test_tax_due_uses_native_currency_precision(self):
		entry = self.make_entry(123.45, 8.5, "445685", insert=False)

		entry.validate()

		expected_tax = flt(
			flt(entry.taxable_base) * flt(entry.tax_rate) / 100,
			entry.precision("tax_due"),
		)
		self.assertEqual(entry.tax_due, expected_tax)

	def test_zero_taxable_base_is_rejected(self):
		entry = self.make_entry(0, 8.5, "445685", insert=False)
		self.assertRaises(frappe.ValidationError, entry.validate)

	def test_negative_taxable_base_is_rejected(self):
		entry = self.make_entry(-100, 8.5, "445685", insert=False)
		self.assertRaises(frappe.ValidationError, entry.validate)

	def test_zero_tax_rate_is_rejected(self):
		entry = self.make_entry(100, 0, "445685", insert=False)
		self.assertRaises(frappe.ValidationError, entry.validate)

	def test_negative_tax_rate_is_rejected(self):
		entry = self.make_entry(100, -8.5, "445685", insert=False)
		self.assertRaises(frappe.ValidationError, entry.validate)

	def test_partial_deduction_is_rejected(self):
		entry = self.make_entry(100, 8.5, "445685", insert=False)
		entry.deductible_tax = 4.25
		self.assertRaises(frappe.ValidationError, entry.insert)

	def test_purchase_invoice_from_other_company_is_rejected(self):
		purchase_invoice = frappe.db.get_value("Purchase Invoice", {"company": ["!=", self.company]}, "name")
		if not purchase_invoice:
			self.skipTest("No Purchase Invoice fixture is available for another company")

		entry = self.make_entry(100, 8.5, "445685", insert=False)
		entry.purchase_invoice = purchase_invoice
		self.assertRaises(frappe.ValidationError, entry.validate)

	def test_account_from_other_company_is_rejected(self):
		other_account = frappe.db.get_value(
			"Account", {"company": ["!=", self.company], "is_group": 0}, "name"
		)
		if not other_account:
			self.skipTest("No account fixture is available for another company")

		entry = frappe.get_doc(
			{
				"doctype": "Import VAT Entry",
				"company": self.company,
				"posting_date": today(),
				"import_reference": "TEST-IMPORT-OTHER-COMPANY",
				"taxable_base": 100,
				"tax_rate": 8.5,
				"tax_due": 8.5,
				"deductible_tax": 8.5,
				"import_vat_due_account": other_account,
				"deductible_tax_account": self.accounts["445685"],
				"naming_series": "IM-VAT-.YYYY.-",
			}
		)
		self.assertRaises(frappe.ValidationError, entry.insert)
