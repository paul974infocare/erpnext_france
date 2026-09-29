# Copyright (c) 2023, Scopen and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt
from erpnext.accounts.utils import is_immutable_ledger_enabled
from erpnext_france.setup import SUPPORTED_ACCOUNTING_COUNTRIES


CANCELLATION_CONTEXT = "_erpnext_france_aen_cancellation_context"
REPOST_CONTEXT = "_erpnext_france_aen_repost_context"
REPOST_METHOD = "erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger.repost"


def prepare_cancellation_accounting_entry_number(doc, method=None):
	if not is_immutable_ledger_enabled():
		return

	key = (doc.doctype, doc.name)
	contexts = getattr(frappe.flags, CANCELLATION_CONTEXT, None)
	if contexts is None:
		contexts = {}
		setattr(frappe.flags, CANCELLATION_CONTEXT, contexts)

	contexts[key] = None
	frappe.db.after_commit.add(lambda: clear_cancellation_accounting_entry_number(key))
	frappe.db.after_rollback.add(lambda: clear_cancellation_accounting_entry_number(key))


def clear_cancellation_accounting_entry_number(doc, method=None):
	key = (doc.doctype, doc.name) if hasattr(doc, "doctype") else doc
	contexts = getattr(frappe.flags, CANCELLATION_CONTEXT, None)
	if not contexts:
		return

	contexts.pop(key, None)
	if not contexts:
		delattr(frappe.flags, CANCELLATION_CONTEXT)


def add_accounting_entry_number(gl_entry, action):
	key = (gl_entry.voucher_type, gl_entry.voucher_no)
	contexts = getattr(frappe.flags, CANCELLATION_CONTEXT, None)
	if contexts is not None and key in contexts:
		if not contexts[key]:
			contexts[key] = get_accounting_number(gl_entry)
		accounting_entry_number = contexts[key]
	else:
		repost_contexts = getattr(frappe.flags, REPOST_CONTEXT, None)
		if repost_contexts is not None and key in repost_contexts:
			context = repost_contexts[key]
			phase = "reversal" if context["reversal_remaining"] else "regeneration"
			accounting_entry_number = context[f"{phase}_number"]
			if not accounting_entry_number:
				accounting_entry_number = get_accounting_number(gl_entry)
				context[f"{phase}_number"] = accounting_entry_number
			if phase == "reversal":
				context["reversal_remaining"] -= 1
		else:
			if gl_entry.accounting_entry_number:
				return

			linked_gl_entries = frappe.get_all(
				"GL Entry",
				fields={"name", "accounting_entry_number"},
				filters={"voucher_no": gl_entry.voucher_no},
			)

			accounting_entry_number = ""
			for linked_gl_entry in linked_gl_entries:
				if linked_gl_entry.name == gl_entry.name:
					continue

				if linked_gl_entry.accounting_entry_number:
					accounting_entry_number = linked_gl_entry.accounting_entry_number

			if not accounting_entry_number:
				accounting_entry_number = get_accounting_number(gl_entry)

	gl_entry.accounting_entry_number = accounting_entry_number
	gl_entry.accounting_journal = get_accounting_journal(gl_entry)

	# Fix precision issues for all currency fields
	gl_entry.credit_in_account_currency = round(
		gl_entry.credit_in_account_currency, gl_entry.precision("credit_in_account_currency")
	)
	gl_entry.debit_in_account_currency = round(
		gl_entry.debit_in_account_currency, gl_entry.precision("debit_in_account_currency")
	)
	gl_entry.credit = round(gl_entry.credit, gl_entry.precision("credit"))
	gl_entry.debit = round(gl_entry.debit, gl_entry.precision("debit"))
	gl_entry.save()


def prepare_repost_accounting_entry_numbers(method=None, kwargs=None, transaction_type=None):
	if method != REPOST_METHOD or not kwargs:
		return

	repost_doc = frappe.get_doc("Repost Accounting Ledger", kwargs["repost_doc_name"])
	if (
		not is_immutable_ledger_enabled()
		or frappe.db.get_value("Company", repost_doc.company, "country")
		not in SUPPORTED_ACCOUNTING_COUNTRIES
	):
		return

	contexts = {}
	try:
		for voucher in repost_doc.vouchers:
			if voucher.status in ("Reposted", "Skipped"):
				continue

			key = (voucher.voucher_type, voucher.voucher_no)
			active_entries = frappe.get_all(
				"GL Entry",
				fields=["name", "debit", "credit"],
				filters={
					"voucher_type": voucher.voucher_type,
					"voucher_no": voucher.voucher_no,
					"is_cancelled": 0,
				},
			)
			# ERPNext v16 has no public phase marker. All five supported paths call
			# make_reverse_gl_entries first; it persists exactly the non-zero active rows,
			# then the voucher's native make_gl_entries path persists regeneration rows.
			contexts[key] = {
				"reversal_remaining": sum(
					1 for entry in active_entries if flt(entry.debit) or flt(entry.credit)
				),
				"reversal_number": None,
				"regeneration_number": None,
			}
	except Exception:
		clear_repost_accounting_entry_numbers(method=REPOST_METHOD)
		raise

	setattr(frappe.flags, REPOST_CONTEXT, contexts)


def clear_repost_accounting_entry_numbers(method=None, kwargs=None, result=None):
	if method != REPOST_METHOD:
		return

	if getattr(frappe.flags, REPOST_CONTEXT, None) is not None:
		delattr(frappe.flags, REPOST_CONTEXT)


def clear_repost_context_on_rollback():
	clear_repost_accounting_entry_numbers(method=REPOST_METHOD)


def get_accounting_journal(entry):
	rules = frappe.get_all(
		"Accounting Journal",
		filters={"company": entry.company, "disabled": 0},
		fields=[
			"name",
			"type",
			"account",
			"`tabAccounting Journal Rule`.document_type",
			"`tabAccounting Journal Rule`.condition",
		],
	)

	applicable_rules = [rule for rule in rules if (rule.account in (entry.account, entry.against, None))]

	if applicable_rules:
		applicable_rules = sorted(
			[rule for rule in applicable_rules if rule.document_type in (entry.voucher_type, None)],
			key=lambda r: r.get("document_type") or "",
			reverse=True,
		)
	else:
		applicable_rules = [rule for rule in rules if rule.document_type == entry.voucher_type]

	accounting_journal = ""
	for condition in [rule for rule in applicable_rules if rule.condition]:
		if frappe.safe_eval(
			condition.condition,
			None,
			{"doc": frappe.get_doc(entry.voucher_type, entry.voucher_no).as_dict()},
		):
			accounting_journal = condition.name
			break

	if not accounting_journal and [rule for rule in applicable_rules if not rule.condition]:
		accounting_journal = next(iter([rule for rule in applicable_rules if not rule.condition])).name

	if not accounting_journal:
		accounting_journal = frappe.db.get_value(
			"GL Entry",
			dict(accounting_entry_number=entry.accounting_entry_number),
			"accounting_journal",
		)

	if not accounting_journal and cint(
		frappe.db.get_single_value("Accounts Settings", "mandatory_accounting_journal")
	):
		frappe.throw(
			_(
				"ERPNext France - Please configure an accounting journal for this transaction type and account: {0}"
			).format(_(entry.voucher_type))
		)

	return accounting_journal


def get_accounting_number(doc: dict) -> str:
	return make_autoname(_("AEN-.fiscal_year.-.#########"), "GL Entry", doc)
