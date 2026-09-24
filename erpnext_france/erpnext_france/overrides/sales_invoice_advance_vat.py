from collections import defaultdict

import frappe
from frappe.utils import flt

SALES_ORDER_REFERENCE = "Sales Order"
PAYMENT_ENTRY_REFERENCE = "Payment Entry"


def make_regional_gl_entries(gl_entries, doc):
	advance_rows = [
		row
		for row in doc.get("advances") or []
		if row.reference_type == PAYMENT_ENTRY_REFERENCE and flt(row.allocated_amount)
	]
	if not advance_rows:
		return gl_entries

	allocations_by_dpi = defaultdict(float)
	dpi_documents = {}
	for row in advance_rows:
		payment_entry = frappe.get_doc(PAYMENT_ENTRY_REFERENCE, row.reference_name)
		_validate_payment_entry(payment_entry, doc)
		dpi_name = payment_entry.down_payment_invoice
		if not dpi_name:
			continue
		down_payment_invoice = dpi_documents.get(dpi_name)
		if down_payment_invoice is None:
			down_payment_invoice = frappe.get_doc("Down Payment Invoice", dpi_name)
			_validate_down_payment_invoice(down_payment_invoice, doc)
			dpi_documents[dpi_name] = down_payment_invoice
		allocations_by_dpi[dpi_name] += flt(row.allocated_amount)

	if not allocations_by_dpi:
		return gl_entries

	advance_vat_account = frappe.db.get_value("Company", doc.company, "default_advance_vat_account")
	if not advance_vat_account:
		frappe.throw("Company default advance VAT account is required to reverse advance VAT")

	for dpi_name, allocated_amount in allocations_by_dpi.items():
		down_payment_invoice = dpi_documents[dpi_name]
		tax_rows = [row for row in down_payment_invoice.get("taxes") or [] if flt(row.tax_amount)]
		if not tax_rows:
			continue
		for row in tax_rows:
			if not row.tax_account:
				frappe.throw("A non-zero Down Payment Invoice tax row must have a tax account")

		precision = _get_currency_precision(down_payment_invoice)
		if not flt(down_payment_invoice.grand_total) or allocated_amount <= 0:
			continue
		payment_entries = _get_payment_entries(down_payment_invoice)
		previous_allocations = _get_previous_allocations(doc, payment_entries, precision)
		cumulative_allocation = previous_allocations + allocated_amount
		cumulative_proportion = min(cumulative_allocation, flt(down_payment_invoice.grand_total))
		cumulative_proportion /= flt(down_payment_invoice.grand_total)

		tax_targets = defaultdict(float)
		for row in tax_rows:
			tax_targets[row.tax_account] += flt(
				flt(row.tax_amount) * cumulative_proportion, precision
			)

		recognized_tax = _get_recognized_tax_by_account(
			down_payment_invoice, tax_targets, payment_entries
		)
		previous_reversed_tax = _get_previous_reversed_tax(
			doc, down_payment_invoice, tax_targets, payment_entries
		)
		for tax_account, target in tax_targets.items():
			previous_tax = previous_reversed_tax.get(tax_account, 0)
			available_tax = max(recognized_tax.get(tax_account, 0) - previous_tax, 0)
			tax_amount = flt(min(max(target - previous_tax, 0), available_tax), precision)
			if not tax_amount:
				continue
			gl_entries.append(
				_make_gl_entry(
					doc,
					tax_account,
					advance_vat_account,
					debit=tax_amount,
					advance_vat_reference=dpi_name,
				)
			)
			gl_entries.append(
				_make_gl_entry(
					doc,
					advance_vat_account,
					tax_account,
					credit=tax_amount,
					advance_vat_reference=dpi_name,
				)
			)

	return gl_entries


def _get_previous_allocations(doc, payment_entries, precision):
	active_sales_invoices = _get_active_sales_invoices(doc)
	if not active_sales_invoices or not payment_entries:
		return 0

	references = frappe.get_all(
		"Sales Invoice Advance",
		filters={
			"parent": ["in", active_sales_invoices],
			"reference_type": PAYMENT_ENTRY_REFERENCE,
			"reference_name": ["in", payment_entries],
		},
		fields=["allocated_amount"],
	)
	return flt(sum(reference.get("allocated_amount") for reference in references), precision)


def _get_previous_reversed_tax(doc, down_payment_invoice, tax_targets, payment_entries):
	active_sales_invoices = _get_active_sales_invoices(doc)
	if not active_sales_invoices or not payment_entries:
		return {}

	entries = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": "Sales Invoice",
			"voucher_no": ["in", active_sales_invoices],
			"is_cancelled": 0,
			"france_advance_vat_reference": down_payment_invoice.name,
			"account": ["in", list(tax_targets)],
		},
		fields=["account", "debit"],
	)
	previous_reversed_tax = defaultdict(float)
	for entry in entries:
		previous_reversed_tax[entry.get("account")] += flt(entry.get("debit"))
	return previous_reversed_tax


def _get_active_sales_invoices(doc):
	return frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "name": ["!=", doc.name]},
		pluck="name",
	)


def _get_payment_entries(down_payment_invoice):
	return frappe.get_all(
		"Payment Entry",
		filters={
			"down_payment_invoice": down_payment_invoice.name,
			"docstatus": 1,
			"payment_type": "Receive",
		},
		pluck="name",
	)


def _validate_payment_entry(payment_entry, doc):
	if payment_entry.docstatus != 1:
		frappe.throw("Payment Entry must be submitted")
	if payment_entry.payment_type != "Receive" or payment_entry.party_type != "Customer":
		frappe.throw("Payment Entry must be a submitted customer receipt")
	if payment_entry.company != doc.company or payment_entry.party != doc.customer:
		frappe.throw("Payment Entry company and customer must match Sales Invoice")


def _validate_down_payment_invoice(down_payment_invoice, doc):
	if down_payment_invoice.docstatus != 1:
		frappe.throw("Down Payment Invoice must be submitted")
	if down_payment_invoice.company != doc.company or down_payment_invoice.customer != doc.customer:
		frappe.throw("Down Payment Invoice company and customer must match Sales Invoice")

	sales_order_currency = frappe.db.get_value(
		SALES_ORDER_REFERENCE, down_payment_invoice.sales_order, "currency"
	)
	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")
	if (
		down_payment_invoice.currency != company_currency
		or sales_order_currency != company_currency
	):
		frappe.throw("Sales Order and Down Payment Invoice currency must match Company currency")

	sales_order_names = {item.sales_order for item in doc.get("items") or [] if item.sales_order}
	if down_payment_invoice.sales_order not in sales_order_names:
		frappe.throw("Down Payment Invoice Sales Order must match Sales Invoice items")


def _get_recognized_tax_by_account(down_payment_invoice, tax_targets, payment_entries=None):
	if payment_entries is None:
		payment_entries = _get_payment_entries(down_payment_invoice)
	if not payment_entries:
		return {}

	entries = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": PAYMENT_ENTRY_REFERENCE,
			"voucher_no": ["in", payment_entries],
			"is_cancelled": 0,
			"france_advance_vat_reference": down_payment_invoice.name,
			"account": ["in", list(tax_targets)],
		},
		fields=["account", "credit"],
	)
	recognized_tax = defaultdict(float)
	for entry in entries:
		recognized_tax[entry.get("account")] += flt(entry.get("credit"))
	return recognized_tax


def _get_currency_precision(document):
	try:
		return document.precision("grand_total")
	except (AttributeError, TypeError):
		return 2


def _make_gl_entry(doc, account, against, debit=0, credit=0, advance_vat_reference=None):
	return doc.get_gl_dict(
		{
			"account": account,
			"against": against,
			"debit": debit,
			"credit": credit,
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
			"debit_in_transaction_currency": debit,
			"credit_in_transaction_currency": credit,
			"cost_center": doc.get("cost_center"),
			"france_advance_vat_reference": advance_vat_reference,
			"_skip_merge": True,
			"post_net_value": True,
		},
		item=doc,
	)
