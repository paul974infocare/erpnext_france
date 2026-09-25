import frappe


LEGACY_CUSTOM_FIELD_NAMES = (
	"Item-is_down_payment_item",
	"Payment Entry-down_payment",
	"Sales Invoice Advance-is_down_payment",
	"Sales Invoice Item-down_payment_rate",
	"Sales Invoice Item-is_down_payment_item",
	"Sales Invoice-down_payment_against",
	"Sales Invoice-down_payment_section",
	"Sales Invoice-down_payment_type",
	"Sales Invoice-down_payment_value",
	"Sales Invoice-get_down_payment",
	"Sales Invoice-is_down_payment_invoice",
)

LEGACY_PROPERTY_SETTER_NAMES = (
	"Item-allow_alternative_item-depends_on",
	"Item-include_item_in_manufacturing-depends_on",
	"Item-is_fixed_asset-depends_on",
	"Item-standard_rate-depends_on",
	"Sales Invoice Advance-allocated_amount-depends_on",
	"Sales Invoice Item-sales_order-read_only_depends_on",
	"Sales Invoice-is_return-depends_on",
	"Sales Invoice-items-read_only_depends_on",
	"Sales Invoice-taxes-read_only_depends_on",
)


def execute():
	for name in LEGACY_CUSTOM_FIELD_NAMES:
		_delete_if_exists("Custom Field", name)

	for name in LEGACY_PROPERTY_SETTER_NAMES:
		_delete_if_exists("Property Setter", name)


def _delete_if_exists(doctype, name):
	if frappe.db.exists(doctype, name):
		frappe.delete_doc(doctype, name, ignore_permissions=True)
