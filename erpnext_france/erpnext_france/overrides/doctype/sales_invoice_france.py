# Copyright (c) 2023, Scopen and contributors
# For license information, please see license.txt
import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.accounts_controller import validate_account_head
from frappe import _

class SalesInvoiceFrance(SalesInvoice):
	def _validate(self):
		super()._validate()

	def set_payment_schedule(self):
		import erpnext.controllers.accounts_controller as ac

		from erpnext_france.controllers.party import get_payment_term_details as our_get_payment_term_details

		frappe.flags.current_doctype = self.doctype

		original = ac.get_payment_term_details
		ac.get_payment_term_details = our_get_payment_term_details
		try:
			super().set_payment_schedule()
		finally:
			ac.get_payment_term_details = original
			frappe.flags.current_doctype

	def validate(self):
		super().validate()

		for item in self.get("items"):
			validate_account_head(
				item.idx,
				item.income_account,
				self.company,
				_("Income", context="Account Validation"),
			)

	def make_item_gl_entries(self, gl_entries):
		before = len(gl_entries)
		super().make_item_gl_entries(gl_entries)

		for gl_entry in gl_entries[before:]:
			gl_entry.setdefault("accounting_journal", self.accounting_journal)

	def validate_due_date(self):
		if self.get("is_pos"):
			return
		from frappe.utils import getdate

		from erpnext_france.controllers.party import validate_due_date as validate_due_date_france

		posting_date = self.posting_date
		if frappe.flags.in_import and getdate(self.due_date) < getdate(posting_date):
			self.due_date = posting_date
		elif self.doctype == "Sales Invoice":
			if not self.due_date:
				frappe.throw(_("Due Date is mandatory"))
			validate_due_date_france(
				posting_date, self.due_date, None, self.payment_terms_template, self.doctype
			)

	def validate_invoice_documents_schedule(self):
		if (
			self.is_return
			or (self.doctype == "Purchase Invoice" and self.is_paid)
			or (self.doctype == "Sales Invoice" and self.is_pos)
			or self.get("is_opening") == "Yes"
		):
			self.payment_terms_template = ""
			self.payment_schedule = []
		if self.is_return:
			return
		self.validate_payment_schedule_dates()
		self.set_payment_schedule()

		self.set_due_date()
		if not self.get("ignore_default_payment_terms_template"):
			self.validate_payment_schedule_amount()
			self.validate_due_date()
		self.validate_advance_entries()
