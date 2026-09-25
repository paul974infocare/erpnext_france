# Copyright (c) 2023, Scopen and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from frappe.utils import flt


class PaymentEntryDownPayment(PaymentEntry):
	def validate(self):
		super().validate()
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

		self._snapshot_down_payment_invoice_amount(down_payment_invoice)

	def _snapshot_down_payment_invoice_amount(self, down_payment_invoice):
		if self.docstatus != 0 and not self.is_new():
			return

		precision = self.precision("down_payment_invoice_amount")
		self.down_payment_invoice_amount = flt(
			sum(
				flt(reference.allocated_amount)
				for reference in self.get("references")
				if reference.reference_doctype == "Sales Order"
				and reference.reference_name == down_payment_invoice.sales_order
			),
			precision,
		)

	def build_gl_map(self):
		# Délègue la construction complète du GL map au core v16 (Advance Payment Ledger inclus),
		# puis injecte le journal comptable France sur les entrées produites.
		gl_entries = super().build_gl_map()
		for gle in gl_entries:
			gle["accounting_journal"] = self.accounting_journal
		return gl_entries
