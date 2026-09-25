from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.erpnext_france.overrides.doctype.payment_entry_down_payment import (
    PaymentEntryDownPayment,
)


class TestPaymentEntryDownPaymentInvoice(FrappeTestCase):
    def make_payment_entry(self):
        payment_entry = frappe.new_doc("Payment Entry")
        payment_entry.company = "Test Company"
        payment_entry.party = "Test Customer"
        payment_entry.down_payment_invoice = "DPI-TEST-0001"
        payment_entry.append(
            "references",
            {
                "reference_doctype": "Sales Order",
                "reference_name": "SO-TEST-0001",
            },
        )
        return payment_entry

    def make_down_payment_invoice(self, **overrides):
        values = {
            "docstatus": 1,
            "company": "Test Company",
            "customer": "Test Customer",
            "sales_order": "SO-TEST-0001",
        }
        values.update(overrides)
        return frappe._dict(values)

    def test_validates_documentary_link(self):
        payment_entry = self.make_payment_entry()
        down_payment_invoice = self.make_down_payment_invoice()

        with patch.object(frappe, "get_doc", return_value=down_payment_invoice):
            PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

    def test_validation_does_not_detect_legacy_sales_invoice_down_payment(self):
        payment_entry = self.make_payment_entry()
        down_payment_invoice = self.make_down_payment_invoice()

        with (
            patch.object(frappe, "get_doc", return_value=down_payment_invoice),
            patch.object(frappe.db, "get_value") as get_value,
        ):
            PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

        get_value.assert_not_called()

    def test_requires_submitted_down_payment_invoice(self):
        payment_entry = self.make_payment_entry()
        down_payment_invoice = self.make_down_payment_invoice(docstatus=0)

        with patch.object(frappe, "get_doc", return_value=down_payment_invoice):
            with self.assertRaises(frappe.ValidationError):
                PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

    def test_requires_matching_company_and_customer(self):
        payment_entry = self.make_payment_entry()

        for fieldname, value in (
            ("company", "Other Company"),
            ("customer", "Other Customer"),
        ):
            down_payment_invoice = self.make_down_payment_invoice(**{fieldname: value})
            with patch.object(frappe, "get_doc", return_value=down_payment_invoice):
                with self.assertRaises(frappe.ValidationError):
                    PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

    def test_requires_sales_order_reference(self):
        payment_entry = self.make_payment_entry()
        payment_entry.references = []
        down_payment_invoice = self.make_down_payment_invoice()

        with patch.object(frappe, "get_doc", return_value=down_payment_invoice):
            with self.assertRaises(frappe.ValidationError):
                PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

    def test_snapshots_only_the_down_payment_sales_order_allocation(self):
        payment_entry = self.make_payment_entry()
        payment_entry.references[0].allocated_amount = 100
        payment_entry.append(
            "references",
            {
                "reference_doctype": "Sales Order",
                "reference_name": "SO-OTHER-0001",
                "allocated_amount": 225.5,
            },
        )
        down_payment_invoice = self.make_down_payment_invoice()

        with (
            patch.object(frappe, "get_doc", return_value=down_payment_invoice),
            patch.object(payment_entry, "precision", return_value=2),
        ):
            PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

        self.assertEqual(payment_entry.down_payment_invoice_amount, 100)

    def test_snapshot_is_not_recalculated_after_submission(self):
        payment_entry = self.make_payment_entry()
        payment_entry.references[0].allocated_amount = 325.5
        down_payment_invoice = self.make_down_payment_invoice()

        with (
            patch.object(frappe, "get_doc", return_value=down_payment_invoice),
            patch.object(payment_entry, "precision", return_value=2),
        ):
            PaymentEntryDownPayment.validate_down_payment_invoice(payment_entry)

        payment_entry.docstatus = 1
        payment_entry.set("__islocal", False)
        payment_entry.references = []
        PaymentEntryDownPayment._snapshot_down_payment_invoice_amount(
            payment_entry, down_payment_invoice
        )

        self.assertEqual(payment_entry.down_payment_invoice_amount, 325.5)