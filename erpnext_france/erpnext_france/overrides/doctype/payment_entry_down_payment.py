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
		self.validate_down_payment_invoice()

	def validate_down_payment_invoice(self):
		if not self.down_payment_invoice:
			return

		down_payment_invoice = frappe.get_doc("Down Payment Invoice", self.down_payment_invoice)
		if down_payment_invoice.docstatus != 1:
			frappe.throw(frappe._("Down Payment Invoice must be submitted"))

		if down_payment_invoice.company != self.company:
			frappe.throw(frappe._("Down Payment Invoice company must match Payment Entry company"))

		if down_payment_invoice.customer != self.party:
			frappe.throw(frappe._("Down Payment Invoice customer must match Payment Entry party"))

		if not any(
			reference.reference_doctype == "Sales Order"
			and reference.reference_name == down_payment_invoice.sales_order
			for reference in self.get("references")
		):
			frappe.throw(frappe._("Payment Entry references must contain the Down Payment Invoice Sales Order"))

	def build_gl_map(self):
		# Délègue la construction complète du GL map au core v16 (Advance Payment Ledger inclus),
		# puis injecte le journal comptable France sur les entrées produites.
		gl_entries = super().build_gl_map()
		for gle in gl_entries:
			gle["accounting_journal"] = self.accounting_journal
		return gl_entries
