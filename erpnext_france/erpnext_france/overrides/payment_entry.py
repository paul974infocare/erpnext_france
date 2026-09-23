from collections import defaultdict

import frappe
from frappe.utils import flt

SALES_ORDER_REFERENCE = "Sales Order"


def add_regional_gl_entries(gl_entries, doc):
	if doc.get("payment_type") != "Receive" or doc.get("party_type") != "Customer":
		return

	down_payment_invoice_name = doc.get("down_payment_invoice")
	if not down_payment_invoice_name:
		return

	down_payment_invoice = frappe.get_doc("Down Payment Invoice", down_payment_invoice_name)
	references = [
		reference
		for reference in doc.get("references") or []
		if reference.reference_doctype == SALES_ORDER_REFERENCE
		and reference.reference_name == down_payment_invoice.sales_order
	]
	if not references:
		return

	if down_payment_invoice.docstatus != 1:
		frappe.throw("Down Payment Invoice must be submitted")
	if down_payment_invoice.company != doc.company:
		frappe.throw("Down Payment Invoice company must match Payment Entry company")
	if down_payment_invoice.customer != doc.party:
		frappe.throw("Down Payment Invoice customer must match Payment Entry party")

	tax_rows = [row for row in down_payment_invoice.get("taxes") or [] if flt(row.tax_amount)]
	if not tax_rows:
		return

	sales_order_currency = _get_sales_order_currency(down_payment_invoice)
	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")
	if down_payment_invoice.currency != company_currency or sales_order_currency != company_currency:
		frappe.throw("Sales Order and Down Payment Invoice currency must match Company currency")

	for row in tax_rows:
		if not row.tax_account:
			frappe.throw("A non-zero Down Payment Invoice tax row must have a tax account")

	advance_vat_account = frappe.db.get_value("Company", doc.company, "default_advance_vat_account")
	if not advance_vat_account:
		frappe.throw("Company default advance VAT account is required to post advance VAT")

	precision = _get_currency_precision(down_payment_invoice)
	current_allocation = flt(sum(reference.allocated_amount for reference in references), precision)
	previous_allocations = _get_previous_allocations(
		doc, down_payment_invoice, precision
	)
	cumulative_allocation = current_allocation + previous_allocations

	tax_targets = defaultdict(float)
	for row in tax_rows:
		tax_total = flt(row.tax_amount)
		target = min(
			tax_total,
			flt(
				tax_total
				* min(cumulative_allocation, flt(down_payment_invoice.grand_total))
				/ flt(down_payment_invoice.grand_total),
				precision,
			),
		)
		tax_targets[row.tax_account] += target

	previous_tax_entries = _get_previous_tax_entries(doc, down_payment_invoice, tax_targets)
	for tax_account, target in tax_targets.items():
		tax_amount = flt(max(target - previous_tax_entries.get(tax_account, 0), 0), precision)
		if not tax_amount:
			continue

		gl_entries.append(
			_make_gl_entry(
				doc,
				advance_vat_account,
				tax_account,
				debit=tax_amount,
				advance_vat_reference=down_payment_invoice.name,
			)
		)
		gl_entries.append(
			_make_gl_entry(
				doc,
				tax_account,
				advance_vat_account,
				credit=tax_amount,
				advance_vat_reference=down_payment_invoice.name,
			)
		)


def _get_currency_precision(document):
	try:
		return document.precision("grand_total")
	except (AttributeError, TypeError):
		return 2


def _get_sales_order_currency(down_payment_invoice):
	sales_order = frappe.db.get_value(
		SALES_ORDER_REFERENCE,
		down_payment_invoice.sales_order,
		"currency",
		as_dict=True,
	)
	if not sales_order or not sales_order.currency:
		frappe.throw("Sales Order currency is required for advance VAT")

	return sales_order.currency


def _get_previous_allocations(doc, down_payment_invoice, precision):
	previous_payment_entries = frappe.get_all(
		"Payment Entry",
		filters={
			"down_payment_invoice": down_payment_invoice.name,
			"docstatus": 1,
			"payment_type": "Receive",
			"name": ["!=", doc.name],
		},
		pluck="name",
	)
	if not previous_payment_entries:
		return 0

	references = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"parent": ["in", previous_payment_entries],
			"reference_doctype": SALES_ORDER_REFERENCE,
			"reference_name": down_payment_invoice.sales_order,
		},
		fields=["allocated_amount"],
	)
	return flt(sum(reference.get("allocated_amount") for reference in references), precision)


def _get_previous_tax_entries(doc, down_payment_invoice, tax_targets):
	previous_payment_entries = frappe.get_all(
		"Payment Entry",
		filters={
			"down_payment_invoice": down_payment_invoice.name,
			"docstatus": 1,
			"payment_type": "Receive",
			"name": ["!=", doc.name],
		},
		pluck="name",
	)
	if not previous_payment_entries:
		return {}

	entries = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": "Payment Entry",
			"voucher_no": ["in", previous_payment_entries],
			"is_cancelled": 0,
			"france_advance_vat_reference": down_payment_invoice.name,
			"account": ["in", list(tax_targets)],
		},
		fields=["account", "credit"],
	)
	previous_tax_entries = defaultdict(float)
	for entry in entries:
		previous_tax_entries[entry.get("account")] += flt(entry.get("credit"))
	return previous_tax_entries


def _make_gl_entry(doc, account, against, debit=0, credit=0, advance_vat_reference=None):
	transaction_exchange_rate = flt(doc.get("transaction_exchange_rate") or 1)
	return doc.get_gl_dict(
		{
			"account": account,
			"against": against,
			"debit": debit,
			"credit": credit,
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
			"debit_in_transaction_currency": debit / transaction_exchange_rate,
			"credit_in_transaction_currency": credit / transaction_exchange_rate,
			"cost_center": doc.get("cost_center"),
			"france_advance_vat_reference": advance_vat_reference,
			"_skip_merge": bool(advance_vat_reference),
			"post_net_value": True,
		},
		item=doc,
	)
