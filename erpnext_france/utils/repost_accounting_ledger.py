import frappe
from frappe import _

from erpnext_france.setup import SUPPORTED_ACCOUNTING_COUNTRIES


def validate_repost_accounting_ledger(doc, method=None):
	if not doc.delete_cancelled_entries:
		return

	country = frappe.db.get_value("Company", doc.company, "country")
	if country in SUPPORTED_ACCOUNTING_COUNTRIES:
		frappe.throw(
			_("Deleting cancelled ledger entries is not permitted for French accounting companies."),
			frappe.ValidationError,
		)