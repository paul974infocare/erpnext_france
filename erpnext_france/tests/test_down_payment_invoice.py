import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from erpnext_france.erpnext_france.erpnext_france.doctype.down_payment_invoice.down_payment_invoice import (
    DownPaymentInvoice,
    make_down_payment_invoice,
)


class TestDownPaymentInvoice(FrappeTestCase):
    def setUp(self):
        self.sales_order = frappe.get_doc("Sales Order", "SAL-ORD-2026-00008")

    def tearDown(self):
        frappe.db.rollback()

    def test_by_percent_totals_and_no_accounting_entries(self):
        doc = make_down_payment_invoice(self.sales_order.name, "ByPercent", 30)

        self.assertEqual(doc.calculation_method, "ByPercent")
        self.assertEqual(doc.advance_percentage, 30)
        self.assertEqual(doc.net_total, 300)
        self.assertEqual(doc.total_taxes_and_charges, 25.5)
        self.assertEqual(doc.grand_total, 325.5)
        self.assertEqual(len(doc.taxes), 1)
        self.assert_no_accounting_entries(doc.name)

    def test_by_amount(self):
        doc = make_down_payment_invoice(self.sales_order.name, "ByAmount", 325.5)

        self.assertEqual(doc.advance_amount, 325.5)
        self.assertEqual(doc.net_total, 300)
        self.assertEqual(doc.total_taxes_and_charges, 25.5)
        self.assertEqual(doc.grand_total, 325.5)

    def test_multiple_tax_rates(self):
        sales_order = frappe._dict(
            {
                "grand_total": 1085,
                "net_total": 1000,
                "total_taxes_and_charges": 85,
                "item_wise_tax_details": [
                    frappe._dict({"rate": 5.5, "taxable_amount": 500, "amount": 27.5}),
                    frappe._dict({"rate": 20, "taxable_amount": 500, "amount": 100}),
                ],
            }
        )

        with patch.object(DownPaymentInvoice, "get_sales_order", return_value=sales_order):
            doc = frappe.new_doc("Down Payment Invoice")
            doc.sales_order = self.sales_order.name
            doc.calculation_method = "ByAmount"
            doc.advance_amount = 325.5
            doc.validate_calculation_method = lambda: None
            doc.calculate_totals()

        self.assertEqual(len(doc.taxes), 2)
        self.assertEqual(sum(row.taxable_amount for row in doc.taxes), 300)
        self.assertEqual(sum(row.tax_amount for row in doc.taxes), 38.25)
        self.assertEqual(doc.grand_total, 338.25)

    def test_submit_cancel_and_no_accounting_entries(self):
        doc = make_down_payment_invoice(self.sales_order.name, "ByAmount", 325.5)
        doc.submit()
        self.assertEqual(doc.docstatus, 1)
        self.assert_no_accounting_entries(doc.name)

        doc.cancel()
        self.assertEqual(doc.docstatus, 2)
        self.assert_no_accounting_entries(doc.name)

    def assert_no_accounting_entries(self, name):
        self.assertFalse(
            frappe.db.exists(
                "GL Entry", {"voucher_type": "Down Payment Invoice", "voucher_no": name}
            )
        )
        self.assertFalse(frappe.db.exists("Payment Ledger Entry", {"voucher_type": "Down Payment Invoice", "voucher_no": name}))
        self.assertFalse(frappe.db.exists("Advance Payment Ledger Entry", {"voucher_type": "Down Payment Invoice", "voucher_no": name}))