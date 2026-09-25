from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.erpnext_france.doctype.down_payment_invoice.down_payment_invoice import (
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
        self.assertEqual(doc.taxes[0].tax_account, "445785 - TVA 8.5% Collectée - IRM1C")
        self.assert_no_accounting_entries(doc.name)

    def test_by_amount(self):
        doc = make_down_payment_invoice(self.sales_order.name, "ByAmount", 325.5)

        self.assertEqual(doc.doctype, "Down Payment Invoice")
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
                    frappe._dict(
                        {
                            "rate": 5.5,
                            "taxable_amount": 500,
                            "amount": 27.5,
                            "tax_row": "tax-row-5-5",
                        }
                    ),
                    frappe._dict(
                        {
                            "rate": 20,
                            "taxable_amount": 500,
                            "amount": 100,
                            "tax_row": "tax-row-20",
                        }
                    ),
                ],
                "taxes": [
                    frappe._dict(
                        {"name": "tax-row-5-5", "account_head": "445755 - TVA 5.5% Collectée - IRM1C"}
                    ),
                    frappe._dict(
                        {"name": "tax-row-20", "account_head": "445720 - TVA 20% Collectée - IRM1C"}
                    ),
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
        self.assertEqual(
            {row.tax_account for row in doc.taxes},
            {
                "445755 - TVA 5.5% Collectée - IRM1C",
                "445720 - TVA 20% Collectée - IRM1C",
            },
        )

    def test_same_tax_rate_with_different_accounts_stays_separate(self):
        sales_order = frappe._dict(
            {
                "grand_total": 1085,
                "net_total": 1000,
                "total_taxes_and_charges": 85,
                "item_wise_tax_details": [
                    frappe._dict(
                        {
                            "rate": 8.5,
                            "taxable_amount": 500,
                            "amount": 42.5,
                            "tax_row": "tax-row-a",
                        }
                    ),
                    frappe._dict(
                        {
                            "rate": 8.5,
                            "taxable_amount": 500,
                            "amount": 42.5,
                            "tax_row": "tax-row-b",
                        }
                    ),
                ],
                "taxes": [
                    frappe._dict({"name": "tax-row-a", "account_head": "Account A"}),
                    frappe._dict({"name": "tax-row-b", "account_head": "Account B"}),
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
        self.assertEqual(
            {(row.tax_rate, row.tax_account) for row in doc.taxes},
            {(8.5, "Account A"), (8.5, "Account B")},
        )

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


class TestDownPaymentInvoicePaymentStatus(FrappeTestCase):
    def make_document(self, grand_total=325.5):
        doc = frappe.new_doc("Down Payment Invoice")
        doc.name = "DPI-TEST-0001"
        doc.sales_order = "SO-TEST-0001"
        doc.grand_total = grand_total
        return doc

    def mock_payment_data(
        self, references, payment_entries, sales_invoices=None, sales_invoice_items=None
    ):
        payment_entries = [
            frappe._dict(
                {
                    "name": entry if isinstance(entry, str) else entry["name"],
                    "down_payment_invoice_amount": 0
                    if isinstance(entry, str)
                    else entry.get("down_payment_invoice_amount", 0),
                    "docstatus": 1 if isinstance(entry, str) else entry.get("docstatus", 1),
                    "payment_type": "Receive" if isinstance(entry, str) else entry.get("payment_type", "Receive"),
                    "company": "Company 1" if isinstance(entry, str) else entry.get("company", "Company 1"),
                    "party_type": "Customer" if isinstance(entry, str) else entry.get("party_type", "Customer"),
                    "party": "Customer 1" if isinstance(entry, str) else entry.get("party", "Customer 1"),
                }
            )
            for entry in payment_entries
        ]
        sales_invoices = sales_invoices or []
        sales_invoice_items = sales_invoice_items or []

        def get_all(doctype, **kwargs):
            if doctype == "Payment Entry":
                return [
                    entry
                    for entry in payment_entries
                    if entry.docstatus == 1
                    and entry.payment_type == "Receive"
                    and entry.company == "Company 1"
                    and entry.party_type == "Customer"
                    and entry.party == "Customer 1"
                ]
            if doctype == "Payment Entry Reference":
                return references
            if doctype == "Sales Invoice":
                names = {
                    invoice if isinstance(invoice, str) else invoice["name"]
                    for invoice in sales_invoices
                }
                return list(names.intersection(kwargs["filters"]["name"][1]))
            if doctype == "Sales Invoice Item":
                return [
                    item
                    for item in sales_invoice_items
                    if item["parent"] in kwargs["filters"]["parent"][1]
                    and item["sales_order"] == kwargs["filters"]["sales_order"]
                ]
            return []

        return patch.object(frappe, "get_all", side_effect=get_all)

    def test_unpaid_without_payments(self):
        doc = self.make_document()

        with self.mock_payment_data([], []):
            self.assertEqual(doc.paid_amount, 0)
            self.assertEqual(doc.outstanding_amount, 325.5)
            self.assertEqual(doc.payment_status, "Unpaid")

    def test_partly_paid(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [
                {
                    "parent": "PE-TEST-0001",
                    "reference_doctype": "Sales Order",
                    "reference_name": "SO-TEST-0001",
                    "allocated_amount": 100,
                }
            ],
            [{"name": "PE-TEST-0001", "down_payment_invoice_amount": 100}],
        ):
            self.assertEqual(doc.paid_amount, 100)
            self.assertEqual(doc.outstanding_amount, 225.5)
            self.assertEqual(doc.payment_status, "Partly Paid")

    def test_paid_with_multiple_payments_and_references(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [
                {"parent": "PE-TEST-0001", "reference_doctype": "Sales Order", "reference_name": "SO-TEST-0001", "allocated_amount": 100},
                {"parent": "PE-TEST-0001", "reference_doctype": "Sales Order", "reference_name": "SO-TEST-0001", "allocated_amount": 25.5},
                {"parent": "PE-TEST-0002", "reference_doctype": "Sales Order", "reference_name": "SO-TEST-0001", "allocated_amount": 200},
                {"parent": "PE-TEST-0003", "reference_doctype": "Sales Order", "reference_name": "SO-TEST-0001", "allocated_amount": 325.5},
            ],
            [
                {"name": "PE-TEST-0001", "down_payment_invoice_amount": 125.5},
                {"name": "PE-TEST-0002", "down_payment_invoice_amount": 200},
            ],
        ):
            self.assertEqual(doc.paid_amount, 325.5)
            self.assertEqual(doc.outstanding_amount, 0)
            self.assertEqual(doc.payment_status, "Paid")

    def test_query_filters_cancelled_entries_and_other_sales_orders(self):
        doc = self.make_document()
        calls = []

        def get_all(doctype, **kwargs):
            calls.append((doctype, kwargs["filters"]))
            if doctype == "Payment Entry":
                self.assertEqual(kwargs["filters"]["down_payment_invoice"], doc.name)
                self.assertEqual(kwargs["filters"]["docstatus"], 1)
                self.assertEqual(kwargs["filters"]["payment_type"], "Receive")
                self.assertEqual(kwargs["filters"]["company"], doc.company)
                self.assertEqual(kwargs["filters"]["party"], doc.customer)
                return [{"name": "PE-TEST-0001", "down_payment_invoice_amount": 100}]
            self.fail(f"Unexpected query for {doctype}")

        with patch.object(frappe, "get_all", side_effect=get_all):
            self.assertEqual(doc.paid_amount, 100)

        self.assertEqual([call[0] for call in calls], ["Payment Entry"])

    def test_relinked_payment_to_sales_invoice_for_same_sales_order_stays_paid(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [
                {
                    "parent": "PE-TEST-0001",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": "SI-TEST-0001",
                    "allocated_amount": 325.5,
                }
            ],
            [{"name": "PE-TEST-0001", "down_payment_invoice_amount": 325.5}],
            sales_invoices=["SI-TEST-0001"],
            sales_invoice_items=[
                {"parent": "SI-TEST-0001", "sales_order": "SO-TEST-0001"}
            ],
        ):
            self.assertEqual(doc.paid_amount, 325.5)
            self.assertEqual(doc.payment_status, "Paid")

    def test_snapshot_keeps_dpi_paid_when_payment_entry_references_are_removed(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [],
            [{"name": "PE-TEST-0001", "down_payment_invoice_amount": 325.5}],
        ):
            self.assertEqual(doc.paid_amount, 325.5)
            self.assertEqual(doc.payment_status, "Paid")

    def test_multiple_payment_entries_and_allocations_are_counted_once(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [
                {
                    "parent": "PE-TEST-0001",
                    "reference_doctype": "Sales Order",
                    "reference_name": "SO-TEST-0001",
                    "allocated_amount": 100,
                },
                {
                    "parent": "PE-TEST-0001",
                    "reference_doctype": "Sales Order",
                    "reference_name": "SO-TEST-0001",
                    "allocated_amount": 25.5,
                },
                {
                    "parent": "PE-TEST-0002",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": "SI-TEST-0001",
                    "allocated_amount": 200,
                },
            ],
            [
                {"name": "PE-TEST-0001", "down_payment_invoice_amount": 125.5},
                {"name": "PE-TEST-0002", "down_payment_invoice_amount": 200},
            ],
            sales_invoices=["SI-TEST-0001"],
            sales_invoice_items=[
                {"parent": "SI-TEST-0001", "sales_order": "SO-TEST-0001"}
            ],
        ):
            self.assertEqual(doc.paid_amount, 325.5)

    def test_cancelled_payment_entry_is_ignored(self):
        doc = self.make_document()

        with self.mock_payment_data(
            [
                {
                    "parent": "PE-TEST-CANCELLED",
                    "reference_doctype": "Sales Order",
                    "reference_name": "SO-TEST-0001",
                    "allocated_amount": 325.5,
                }
            ],
            [{"name": "PE-TEST-CANCELLED", "docstatus": 2}],
        ):
            self.assertEqual(doc.paid_amount, 0)
            self.assertEqual(doc.payment_status, "Unpaid")
