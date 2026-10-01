# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import format_datetime
from frappe.utils.data import get_datetime_in_timezone
from pypika import Order

COLUMNS = [
	{
		"label": _("JournalCode"),
		"fieldname": "JournalCode",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("JournalLib"),
		"fieldname": "JournalLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureNum"),
		"fieldname": "EcritureNum",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureDate"),
		"fieldname": "EcritureDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("CompteNum"),
		"fieldname": "CompteNum",
		"fieldtype": "Link",
		"options": "Account",
		"width": 100,
	},
	{
		"label": _("CompteLib"),
		"fieldname": "CompteLib",
		"fieldtype": "Link",
		"options": "Account",
		"width": 200,
	},
	{
		"label": _("CompAuxNum"),
		"fieldname": "CompAuxNum",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("CompAuxLib"),
		"fieldname": "CompAuxLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("PieceRef"),
		"fieldname": "PieceRef",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("PieceDate"),
		"fieldname": "PieceDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("EcritureLib"),
		"fieldname": "EcritureLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": "Débit",
		"fieldname": "Debit",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": "Crédit",
		"fieldname": "Credit",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureLet"),
		"fieldname": "EcritureLet",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("DateLet"),
		"fieldname": "DateLet",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("ValidDate"),
		"fieldname": "ValidDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("Montantdevise"),
		"fieldname": "Montantdevise",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Idevise"),
		"fieldname": "Idevise",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Due Date"),
		"fieldname": "DateLimitReglmt",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("Num Facture"),
		"fieldname": "NumFacture",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Export Date"),
		"fieldname": "ExportDate",
		"fieldtype": "Datetime",
		"width": 90,
	},
	{
		"label": _("GL Entry"),
		"fieldname": "GlName",
		"fieldtype": "Link",
		"options": "GL Entry",
		"width": 0,
	},
]


def execute(filters=None):
	validate_filters(filters)
	return COLUMNS, get_result(
		company=filters["company"],
		fiscal_year=filters["fiscal_year"],
		from_date=filters["from_date"],
		to_date=filters["to_date"],
		hide_already_exported=True if filters.get("hide_already_exported") else False,
	)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("{0} is mandatory").format(_("Company")))

	if not filters.get("fiscal_year"):
		frappe.throw(_("{0} is mandatory").format(_("Fiscal Year")))


def get_gl_entries(company, fiscal_year, from_date, to_date, hide_already_exported):
	company_doc = frappe.get_doc("Company", company)
	gle = frappe.qb.DocType("GL Entry")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	purchase_invoice = frappe.qb.DocType("Purchase Invoice")
	journal_entry = frappe.qb.DocType("Journal Entry")
	payment_entry = frappe.qb.DocType("Payment Entry")
	customer = frappe.qb.DocType("Customer")
	supplier = frappe.qb.DocType("Supplier")
	employee = frappe.qb.DocType("Employee")

	debit = frappe.query_builder.functions.Sum(gle.debit).as_("debit")
	credit = frappe.query_builder.functions.Sum(gle.credit).as_("credit")
	debit_currency = frappe.query_builder.functions.Sum(gle.debit_in_account_currency).as_("debitCurr")
	credit_currency = frappe.query_builder.functions.Sum(gle.credit_in_account_currency).as_("creditCurr")
	debit_transaction_currency = frappe.query_builder.functions.Sum(
		gle.debit_in_transaction_currency
	).as_("debitTransactionCurr")
	credit_transaction_currency = frappe.query_builder.functions.Sum(
		gle.credit_in_transaction_currency
	).as_("creditTransactionCurr")

	query = (
		frappe.qb.from_(gle)
		.left_join(sales_invoice)
		.on(gle.voucher_no == sales_invoice.name)
		.left_join(purchase_invoice)
		.on(gle.voucher_no == purchase_invoice.name)
		.left_join(journal_entry)
		.on(gle.voucher_no == journal_entry.name)
		.left_join(payment_entry)
		.on(gle.voucher_no == payment_entry.name)
		.left_join(customer)
		.on(gle.party == customer.name)
		.left_join(supplier)
		.on(gle.party == supplier.name)
		.left_join(employee)
		.on(gle.party == employee.name)
		.select(
			gle.posting_date.as_("GlPostDate"),
			gle.name.as_("GlName"),
			gle.account,
			gle.is_opening,
			gle.transaction_date,
			gle.transaction_currency,
			gle.export_date.as_("ExportDate"),
			debit,
			credit,
			debit_currency,
			credit_currency,
			debit_transaction_currency,
			credit_transaction_currency,
			gle.accounting_entry_number,
			gle.voucher_type,
			gle.voucher_no,
			gle.against_voucher_type,
			gle.against_voucher,
			gle.account_currency,
			gle.against,
			gle.party_type,
			gle.party,
			gle.accounting_journal,
			gle.remarks,
			sales_invoice.name.as_("InvName"),
			sales_invoice.title.as_("InvTitle"),
			sales_invoice.posting_date.as_("InvPostDate"),
			sales_invoice.due_date.as_("InvDueDate"),
			purchase_invoice.name.as_("PurName"),
			purchase_invoice.title.as_("PurTitle"),
			purchase_invoice.posting_date.as_("PurPostDate"),
			purchase_invoice.bill_date.as_("PurBillDate"),
			purchase_invoice.due_date.as_("PurDueDate"),
			journal_entry.cheque_no.as_("JnlRef"),
			journal_entry.posting_date.as_("JnlPostDate"),
			journal_entry.title.as_("JnlTitle"),
			payment_entry.name.as_("PayName"),
			payment_entry.posting_date.as_("PayPostDate"),
			payment_entry.title.as_("PayTitle"),
			customer.customer_name,
			customer.name.as_("cusName"),
			supplier.supplier_name,
			supplier.name.as_("supName"),
			employee.employee_name,
			employee.name.as_("empName"),
		)
		.where(
			(gle.company == company)
			& (gle.fiscal_year == fiscal_year)
			& (gle.posting_date >= from_date)
			& (gle.posting_date <= to_date)
		)
	)

	if hide_already_exported:
		query = query.where(gle.export_date.isnull())

	query = query.groupby(gle.voucher_type, gle.voucher_no, gle.account, gle.name, gle.accounting_entry_number)
	query = get_fec_query_order(query, gle, company_doc.type_export_fec)

	return query.run(as_dict=True)


def get_fec_query_order(query, gle, type_export_fec):
	if type_export_fec == "Standard FEC Export":
		return query.orderby(gle.accounting_entry_number, order=Order.asc).orderby(gle.name, order=Order.asc)

	return (
		query.orderby(gle.posting_date, order=Order.desc)
		.orderby(gle.voucher_no, order=Order.asc)
		.orderby(gle.accounting_entry_number, order=Order.asc)
	)


def get_result(company, fiscal_year, from_date, to_date, hide_already_exported):
	data = get_gl_entries(company, fiscal_year, from_date, to_date, hide_already_exported)

	result = []

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	account_code_length = frappe.db.get_value("Company", company, "account_code_length") or 0
	accounts = frappe.get_all(
		"Account",
		filters={"Company": company},
		fields=["name", "account_number", "account_name"],
	)
	journals = get_accounting_journals(company)

	for d in data:
		JournalCode, JournalLib = get_journal_values(d, journals)
		EcritureNum = d.get("accounting_entry_number")
		GlName = d.get("GlName")

		DateLimitReglmt = ""
		NumFacture = ""
		EcritureDate = format_datetime(d.get("GlPostDate"), "yyyyMMdd")
		ExportDate = format_datetime(d.get("ExportDate"), "yyyy-MM-dd HH:mm")
		PieceDate = EcritureDate

		account_number = [
			{"account_number": account.account_number, "account_name": account.account_name}
			for account in accounts
			if account.name == d.get("account") and account.account_number
		]
		if account_number:
			original = account_number[0]["account_number"]
			CompteLib = account_number[0]["account_name"]
			# Apply zero-padding as suffix if configured
			if account_code_length > 0 and len(original) < account_code_length:
				CompteNum = original.ljust(account_code_length, "0")
			else:
				CompteNum = original
			# CompteLib = account_number[0]["account_name"]
		else:
			frappe.throw(
				_(
					"Account number for account {0} is not available.<br> Please setup your Chart of Accounts correctly."
				).format(d.get("account"))
			)

		if d.get("party_type") == "Customer":
			party_accounts = frappe.get_all(
				"Party Account",
				filters={"Company": company, "parent": d.get("cusName"), "parenttype": "Customer"},
				fields=["subledger_account"],
			)
			if party_accounts and party_accounts[0].get("subledger_account"):
				CompAuxNum = party_accounts[0].get("subledger_account")
			else:
				CompAuxNum = d.get("cusName")

			CompAuxLib = d.get("customer_name")

		elif d.get("party_type") == "Supplier":
			party_accounts = frappe.get_all(
				"Party Account",
				filters={"Company": company, "parent": d.get("supName"), "parenttype": "Supplier"},
				fields=["subledger_account"],
			)
			if party_accounts and party_accounts[0].get("subledger_account"):
				CompAuxNum = party_accounts[0].get("subledger_account")
			else:
				CompAuxNum = d.get("supName")
			CompAuxLib = d.get("supplier_name")

		elif d.get("party_type") == "Employee":
			CompAuxNum = d.get("empName")
			CompAuxLib = d.get("employee_name")

		elif d.get("party_type") == "Student":
			CompAuxNum = d.get("stuName")
			CompAuxLib = d.get("student_name")

		elif d.get("party_type") == "Member":
			CompAuxNum = d.get("memName")
			CompAuxLib = d.get("member_name")

		else:
			CompAuxNum = ""
			CompAuxLib = ""

		ValidDate = format_datetime(d.get("GlPostDate"), "yyyyMMdd")

		PieceRef = d.get("voucher_no") or "Sans Reference"
		# PieceRefType = d.get("voucher_type") or "Sans Reference"

		if d.get("voucher_type") == "Sales Invoice":
			NumFacture = d.get("voucher_no")
			DateLimitReglmt = format_datetime(d.get("InvDueDate"), "yyyyMMdd")
			PieceDate = format_datetime(d.get("InvPostDate"), "yyyyMMdd")

		if d.get("voucher_type") == "Purchase Invoice":
			NumFacture = d.get("voucher_no")
			DateLimitReglmt = format_datetime(d.get("PurDueDate"), "yyyyMMdd")
			PieceDate = format_datetime(d.get("PurBillDate") or d.get("PurPostDate"), "yyyyMMdd")

		# EcritureLib is the reference title unless it is an opening entry
		if d.get("is_opening") == "Yes":
			EcritureLib = _("Opening Entry Journal")
		elif d.get("remarks") and d.get("remarks").lower() not in ("no remarks", _("no remarks")):
			EcritureLib = d.get("remarks")
		elif d.get("voucher_type") == "Sales Invoice":
			EcritureLib = d.get("InvTitle")
		elif d.get("voucher_type") == "Purchase Invoice":
			EcritureLib = d.get("PurTitle")
		elif d.get("voucher_type") == "Journal Entry":
			EcritureLib = d.get("JnlTitle")
		elif d.get("voucher_type") == "Payment Entry":
			EcritureLib = d.get("PayTitle")
		else:
			EcritureLib = d.get("voucher_type")

		EcritureLib = " ".join((EcritureLib or "").splitlines()) or d.get("voucher_type")

		debit = "{:.2f}".format(d.get("debit")).replace(".", ",")

		credit = "{:.2f}".format(d.get("credit")).replace(".", ",")

		if d.debit == d.credit == 0:
			continue

		Montantdevise, Idevise = get_transaction_currency_values(d, company_currency)

		EcritureLet = ""
		DateLet = ""

		row = [
			JournalCode,
			JournalLib,
			EcritureNum,
			EcritureDate,
			CompteNum,
			CompteLib,
			CompAuxNum,
			CompAuxLib,
			PieceRef,
			PieceDate,
			EcritureLib,
			debit,
			credit,
			EcritureLet,
			DateLet or "",
			ValidDate,
			Montantdevise,
			Idevise,
			DateLimitReglmt,
			NumFacture,
			ExportDate,
			GlName,
		]

		result.append(row)

	return result


def get_accounting_journals(company):
	journals = frappe.get_all(
		"Accounting Journal",
		filters={"company": company},
		fields=["name", "journal_code", "journal_name"],
	)
	return {
		"by_name": {
			journal["name"]: (journal["journal_code"], journal["journal_name"]) for journal in journals
		},
		"by_code": {journal["journal_code"]: journal["journal_name"] for journal in journals},
	}


def get_journal_values(entry, journals):
	accounting_journal = entry.get("accounting_journal")
	if accounting_journal:
		return journals["by_name"].get(accounting_journal, ("", ""))

	journal_code = re.split("-|/|[0-9]", entry.get("voucher_no"))[0]
	return journal_code, journals["by_code"].get(journal_code)


def get_transaction_currency_values(entry, company_currency):
	transaction_currency = entry.get("transaction_currency")
	if not transaction_currency or transaction_currency == company_currency:
		return "", ""

	debit = entry.get("debitTransactionCurr") or 0
	credit = entry.get("creditTransactionCurr") or 0
	amount = debit if debit != 0 else -credit
	return "{:.2f}".format(amount).replace(".", ","), transaction_currency
