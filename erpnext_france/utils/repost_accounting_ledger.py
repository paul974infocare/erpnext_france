import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.general_ledger import process_gl_map
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from erpnext.accounts.utils import is_immutable_ledger_enabled
from erpnext_france.setup import SUPPORTED_ACCOUNTING_COUNTRIES


GL_SUBSTANCE_FIELDS = {
	"account",
	"account_currency",
	"against",
	"against_voucher",
	"against_voucher_type",
	"company",
	"cost_center",
	"credit",
	"credit_in_account_currency",
	"credit_in_transaction_currency",
	"debit",
	"debit_in_account_currency",
	"debit_in_transaction_currency",
	"finance_book",
	"is_opening",
	"party",
	"party_type",
	"posting_date",
	"project",
	"transaction_currency",
	"transaction_date",
	"transaction_exchange_rate",
	"voucher_detail_no",
	"voucher_no",
	"voucher_subtype",
	"voucher_type",
}
# remarks feeds FEC EcritureLib, but native Repost preview/gl_map does not reliably
# reproduce the final persisted label before GL Entry persistence; it is not usable here.
AMOUNT_GL_FIELDS = {
	"debit",
	"credit",
	"debit_in_account_currency",
	"credit_in_account_currency",
	"debit_in_transaction_currency",
	"credit_in_transaction_currency",
}
INVERSE_AMOUNT_FIELDS = {
	"debit": "credit",
	"credit": "debit",
	"debit_in_account_currency": "credit_in_account_currency",
	"credit_in_account_currency": "debit_in_account_currency",
	"debit_in_transaction_currency": "credit_in_transaction_currency",
	"credit_in_transaction_currency": "debit_in_transaction_currency",
}
REPOST_VOUCHER_TYPES = {
	"Sales Invoice",
	"Purchase Invoice",
	"Purchase Receipt",
	"Payment Entry",
	"Journal Entry",
}
MISSING_GL_VALUE = object()


def _get_active_gl_entries(voucher_type, voucher_no):
	return frappe.get_all(
		"GL Entry",
		fields=["*"],
		filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
	)


def _get_expected_gl_entries(doc):
	if doc.doctype not in REPOST_VOUCHER_TYPES:
		return None

	if doc.doctype in ("Payment Entry", "Journal Entry"):
		gl_map = doc.build_gl_map()
		merge_entries = frappe.get_single_value("Accounts Settings", "merge_similar_account_heads")
	elif doc.doctype == "Purchase Receipt":
		gl_map = doc.get_gl_entries(doc.get_inventory_account_map())
		merge_entries = False
	else:
		gl_map = doc.get_gl_entries()
		merge_entries = False

	return process_gl_map(gl_map, merge_entries=merge_entries, from_repost=True)


def _normalize_gl_value(fieldname, value):
	if value is MISSING_GL_VALUE:
		return MISSING_GL_VALUE if fieldname in AMOUNT_GL_FIELDS else ""
	if fieldname in AMOUNT_GL_FIELDS:
		return flt(value, 9)
	if value is None:
		return ""
	return str(value) if hasattr(value, "isoformat") else value


def _gl_value(entry, fieldname):
	return _normalize_gl_value(fieldname, entry[fieldname] if fieldname in entry else MISSING_GL_VALUE)


def _get_gl_fieldnames(*entry_groups):
	accounting_dimensions = set(get_accounting_dimensions())
	return sorted(
		{
			fieldname
			for entries in entry_groups
			for entry in entries or []
			for fieldname in entry.keys()
			if fieldname in GL_SUBSTANCE_FIELDS | accounting_dimensions
		}
	)


def _gl_substance(entries, fieldnames):
	entries = list(entries or [])
	amount_fields = sorted(AMOUNT_GL_FIELDS & set(fieldnames))
	identity_fields = [fieldname for fieldname in fieldnames if fieldname not in AMOUNT_GL_FIELDS]
	merged = {}

	for entry in entries:
		identity = tuple(
			(fieldname, _gl_value(entry, fieldname))
			for fieldname in identity_fields
		)
		identity += (("__amount_fields_present__", tuple(fieldname for fieldname in amount_fields if fieldname in entry)),)
		row = merged.setdefault(identity, {fieldname: 0 for fieldname in amount_fields})
		for fieldname in amount_fields:
			if fieldname in entry:
				row[fieldname] += _gl_value(entry, fieldname)

	return sorted(
		[
			(identity, tuple((fieldname, flt(row[fieldname], 9)) for fieldname in amount_fields))
			for identity, row in merged.items()
		],
		key=repr,
	)


def _gl_sort_key(entry, fieldnames):
	return tuple(
		(fieldname, repr(_gl_value(entry, fieldname)))
		for fieldname in fieldnames
	)


def _gl_pair_key(entry, fieldnames):
	return tuple(
		(fieldname, _gl_value(entry, fieldname))
		for fieldname in fieldnames
		if fieldname not in AMOUNT_GL_FIELDS and fieldname != "posting_date"
	)


def _is_inverse_gl_entry(entry, candidate, fieldnames):
	if _gl_pair_key(entry, fieldnames) != _gl_pair_key(candidate, fieldnames):
		return False

	return all(
		_gl_value(entry, fieldname)
		== _gl_value(candidate, INVERSE_AMOUNT_FIELDS[fieldname])
		for fieldname in AMOUNT_GL_FIELDS
	)


def _reduce_neutralized_gl_entries(entries, fieldnames):
	"""Remove exact reversal pairs while retaining dates on unmatched entries."""
	remaining = sorted(entries or [], key=lambda entry: _gl_sort_key(entry, fieldnames))
	residual = []

	while remaining:
		entry = remaining.pop(0)
		inverse_index = next(
			(
				index
				for index, candidate in enumerate(remaining)
				if _is_inverse_gl_entry(entry, candidate, fieldnames)
			),
			None,
		)
		if inverse_index is None:
			residual.append(entry)
		else:
			remaining.pop(inverse_index)

	return residual


def _repost_changes_accounting(doc):
	active = _get_active_gl_entries(doc.doctype, doc.name)
	expected = _get_expected_gl_entries(doc)
	if expected is None:
		return False

	fieldnames = _get_gl_fieldnames(active, expected)
	active = _reduce_neutralized_gl_entries(active, fieldnames)
	return _gl_substance(active, fieldnames) != _gl_substance(expected, fieldnames)


def _with_repost_context(function):
	previous = getattr(frappe.flags, "through_repost_accounting_ledger", None)
	frappe.flags.through_repost_accounting_ledger = True
	try:
		return function()
	finally:
		frappe.flags.through_repost_accounting_ledger = previous


def validate_repost_accounting_ledger(doc, method=None):
	country = frappe.db.get_value("Company", doc.company, "country")
	if country not in SUPPORTED_ACCOUNTING_COUNTRIES:
		return

	if doc.delete_cancelled_entries:
		frappe.throw(
			_("Deleting cancelled ledger entries is not permitted for French accounting companies."),
			frappe.ValidationError,
		)

	if not is_immutable_ledger_enabled():
		return

	unchanged = []
	for voucher in doc.vouchers:
		voucher_doc = frappe.get_doc(voucher.voucher_type, voucher.voucher_no)
		if not _with_repost_context(lambda: not _repost_changes_accounting(voucher_doc)):
			continue
		unchanged.append(f"{voucher.voucher_type} {voucher.voucher_no}")

	if unchanged:
		frappe.throw(
			_("Repost is blocked because it would not change the accounting entries: {0}").format(
				", ".join(unchanged)
			),
			frappe.ValidationError,
		)
