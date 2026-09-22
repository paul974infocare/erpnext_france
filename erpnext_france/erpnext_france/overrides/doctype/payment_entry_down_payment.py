# Copyright (c) 2023, Scopen and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from frappe.utils import cint


class PaymentEntryDownPayment(PaymentEntry):
	def validate(self):
		super().validate()
		self.check_if_down_payment()

	def check_if_down_payment(self):
		is_down_payment = False
		for d in self.get("references"):
			if d.reference_doctype == "Sales Invoice":
				is_dp_invoice = frappe.db.get_value(
					d.reference_doctype, d.reference_name, "is_down_payment_invoice"
				)
				if cint(is_dp_invoice):
					is_down_payment = True
		self.down_payment = is_down_payment

	def build_gl_map(self):
		# Délègue la construction complète du GL map au core v16 (Advance Payment Ledger inclus),
		# puis injecte le journal comptable France sur les entrées produites.
		gl_entries = super().build_gl_map()
		for gle in gl_entries:
			gle["accounting_journal"] = self.accounting_journal
		return gl_entries
