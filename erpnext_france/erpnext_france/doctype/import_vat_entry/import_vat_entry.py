import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ImportVATEntry(Document):
	def validate(self):
		self.validate_tax_values()
		self.validate_linked_documents()
		self.validate_accounts()
		self.validate_deduction()
		self.validate_existing_journal_entry()

	def validate_tax_values(self):
		if flt(self.taxable_base) <= 0:
			frappe.throw(_("Import VAT Taxable Base must be greater than zero"))

		if flt(self.tax_rate) <= 0:
			frappe.throw(_("Tax Rate must be greater than zero"))

		self.tax_due = flt(
			flt(self.taxable_base) * flt(self.tax_rate) / 100,
			self.precision("tax_due"),
		)

	def validate_linked_documents(self):
		for doctype, fieldname in (
			("Purchase Invoice", "purchase_invoice"),
			("Purchase Receipt", "purchase_receipt"),
		):
			name = self.get(fieldname)
			if name and frappe.db.get_value(doctype, name, "company") != self.company:
				frappe.throw(_("{0} must belong to company {1}").format(doctype, self.company))

	def validate_accounts(self):
		for fieldname in ("import_vat_due_account", "deductible_tax_account"):
			account = self.get(fieldname)
			if not account:
				frappe.throw(_("{0} is required").format(self.meta.get_label(fieldname)))
			if frappe.db.get_value("Account", account, "company") != self.company:
				frappe.throw(_("Account {0} must belong to company {1}").format(account, self.company))
			if frappe.db.get_value("Account", account, "is_group"):
				frappe.throw(_("Account {0} must be a ledger account").format(account))

	def validate_deduction(self):
		if flt(
			self.deductible_tax,
			self.precision("deductible_tax"),
		) != flt(
			self.tax_due,
			self.precision("tax_due"),
		):
			frappe.throw(
				_(
					"Partial import VAT deduction is not supported by M1 until a native accounting treatment is available"
				)
			)

	def validate_existing_journal_entry(self):
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") != 2:
			frappe.throw(_("This Import VAT Entry already has an active Journal Entry"))

	def on_submit(self):
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Journal Entry"
		journal_entry.company = self.company
		journal_entry.posting_date = self.posting_date
		journal_entry.user_remark = _("Import VAT Entry {0}").format(self.name)
		journal_entry.append(
			"accounts",
			{
				"account": self.deductible_tax_account,
				"debit_in_account_currency": self.deductible_tax,
			},
		)
		journal_entry.append(
			"accounts",
			{
				"account": self.import_vat_due_account,
				"credit_in_account_currency": self.tax_due,
			},
		)
		journal_entry.insert()
		journal_entry.submit()
		self.db_set("journal_entry", journal_entry.name)

	def on_cancel(self):
		if not self.journal_entry:
			return

		journal_entry = frappe.get_doc("Journal Entry", self.journal_entry)
		if journal_entry.docstatus == 1:
			journal_entry.cancel()
		elif journal_entry.docstatus == 0:
			frappe.throw(_("The generated Journal Entry must be submitted before cancellation"))
