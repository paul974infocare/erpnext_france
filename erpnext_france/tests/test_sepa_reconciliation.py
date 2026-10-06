from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_france.regional.france.sepa_utils import (
    auto_reconcile_sepa_transaction,
    reconcile_bank_transaction_to_sepa_line,
)


class TestSEPAReconciliation(FrappeTestCase):
    def test_auto_reconciliation_rolls_back_failed_attempt_to_savepoint(self):
        bank_transaction = frappe._dict(
            {
                "name": "BANK-TRANSACTION-ATOMICITY-0001",
                "description": "Payment TEST-20261005-ABCDEF07",
                "reference_number": None,
                "transaction_id": None,
                "bank_party_name": None,
            }
        )

        with (
            patch(
                "frappe.db.get_value",
                return_value="SEPA-LINE-ATOMICITY-0001",
            ),
            patch("frappe.db.savepoint") as savepoint,
            patch("frappe.db.rollback") as rollback,
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "reconcile_bank_transaction_to_sepa_line",
                side_effect=frappe.ValidationError("Simulated reconciliation failure"),
            ),
            patch("frappe.log_error") as log_error,
        ):
            auto_reconcile_sepa_transaction(bank_transaction, "on_submit")

        savepoint.assert_called_once()
        rollback.assert_called_once()

        savepoint_name = savepoint.call_args.args[0]
        rollback.assert_called_once_with(save_point=savepoint_name)
        log_error.assert_called_once()


    def test_reconciliation_links_created_payment_entry_to_bank_transaction(self):
        sepa_line = frappe._dict(
            {
                "name": "SEPA-LINE-TEST-0001",
                "parent": "SEPA-BORDEREAU-TEST-0001",
                "invoice": "PINV-TEST-0001",
                "invoice_type": "Purchase Invoice",
                "party": "Test Supplier",
                "party_type": "Supplier",
                "amount": 125.50,
                "mandate": None,
                "status": "Pending",
            }
        )

        bordereau = frappe._dict(
            {
                "name": "SEPA-BORDEREAU-TEST-0001",
                "company": "Test Company",
                "bank_account": "Test Company Bank",
                "payment_type": "Credit",
            }
        )

        bank_transaction = frappe._dict(
            {
                "name": "BANK-TRANSACTION-TEST-0001",
                "unallocated_amount": 125.50,
                "deposit": 0,
                "withdrawal": 125.50,
                "date": "2026-10-02",
            }
        )

        invoice = frappe._dict(
            {
                "name": "PINV-TEST-0001",
                "payment_terms_template": None,
                "payment_schedule": [],
            }
        )

        payment_entry = MagicMock()
        payment_entry.name = "PE-TEST-0001"

        def get_doc_side_effect(doctype, name=None, *args, **kwargs):
            if isinstance(doctype, dict):
                return payment_entry
            if doctype == "SEPA Payment Bordereau":
                return bordereau
            if doctype == "Bank Transaction":
                return bank_transaction
            if doctype == "Purchase Invoice":
                return invoice
            raise AssertionError(f"Unexpected frappe.get_doc call: {doctype}, {name}")

        def get_value_side_effect(doctype, filters=None, fieldname=None, *args, **kwargs):
            if doctype == "SEPA Payment Bordereau Line":
                return sepa_line
            if doctype == "Bank Account":
                return "Test Bank GL - TC"
            raise AssertionError(
                f"Unexpected frappe.db.get_value call: {doctype}, {filters}, {fieldname}"
            )

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
            patch("frappe.db.set_value"),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_payment_entry_account_fields",
                return_value=("Pay", {}),
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_remittance_info",
                return_value="SEPA test",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_invoice_reference",
                return_value="PINV-TEST-0001",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "sync_invoice_sepa_bordereau_link"
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "update_bordereau_status"
            ),
            patch("frappe.msgprint"),
            patch(
                "erpnext.accounts.doctype.bank_reconciliation_tool."
                "bank_reconciliation_tool.reconcile_vouchers"
            ) as reconcile_vouchers,
        ):
            result = reconcile_bank_transaction_to_sepa_line(
                bank_transaction.name,
                "TEST-20261002-ABCDEF03",
            )

        self.assertEqual(result, payment_entry.name)
        payment_entry.insert.assert_called_once_with()
        payment_entry.submit.assert_called_once_with()

        reconcile_vouchers.assert_called_once()
        args, kwargs = reconcile_vouchers.call_args
        self.assertEqual(args[0], bank_transaction.name)

    def test_reconciliation_rejects_bank_transaction_amount_mismatch(self):
        sepa_line = frappe._dict(
            {
                "name": "SEPA-LINE-TEST-0002",
                "parent": "SEPA-BORDEREAU-TEST-0002",
                "invoice": "PINV-TEST-0002",
                "invoice_type": "Purchase Invoice",
                "party": "Test Supplier",
                "party_type": "Supplier",
                "amount": 125.50,
                "mandate": None,
                "status": "Pending",
            }
        )

        bordereau = frappe._dict(
            {
                "name": "SEPA-BORDEREAU-TEST-0002",
                "company": "Test Company",
                "bank_account": "Test Company Bank",
                "payment_type": "Credit",
            }
        )

        bank_transaction = frappe._dict(
            {
                "name": "BANK-TRANSACTION-TEST-0002",
                "unallocated_amount": 130.00,
                "date": "2026-10-02",
            }
        )

        def get_doc_side_effect(doctype, name=None, *args, **kwargs):
            if isinstance(doctype, dict):
                raise AssertionError(
                    "Payment Entry must not be created when SEPA and bank amounts differ"
                )
            if doctype == "SEPA Payment Bordereau":
                return bordereau
            if doctype == "Bank Transaction":
                return bank_transaction
            raise AssertionError(f"Unexpected frappe.get_doc call: {doctype}, {name}")

        def get_value_side_effect(doctype, filters=None, fieldname=None, *args, **kwargs):
            if doctype == "SEPA Payment Bordereau Line":
                return sepa_line
            if doctype == "Bank Account":
                return "Test Bank GL - TC"
            raise AssertionError(
                f"Unexpected frappe.db.get_value call: {doctype}, {filters}, {fieldname}"
            )

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
            patch("frappe.db.set_value") as set_value,
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_payment_entry_account_fields",
                return_value=("Pay", {}),
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_remittance_info",
                return_value="SEPA test",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_invoice_reference",
                return_value="PINV-TEST-0002",
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                reconcile_bank_transaction_to_sepa_line(
                    bank_transaction.name,
                    "TEST-20261002-ABCDEF04",
                )

        set_value.assert_not_called()


    def test_reconciliation_accepts_debit_sepa_bank_deposit(self):
        sepa_line = frappe._dict(
            {
                "name": "SEPA-LINE-TEST-0004",
                "parent": "SEPA-BORDEREAU-TEST-0004",
                "invoice": "SINV-TEST-0004",
                "invoice_type": "Sales Invoice",
                "party": "Test Customer",
                "party_type": "Customer",
                "amount": 125.50,
                "mandate": None,
                "status": "Pending",
            }
        )

        bordereau = frappe._dict(
            {
                "name": "SEPA-BORDEREAU-TEST-0004",
                "company": "Test Company",
                "bank_account": "Test Company Bank",
                "payment_type": "Debit",
            }
        )

        bank_transaction = frappe._dict(
            {
                "name": "BANK-TRANSACTION-TEST-0004",
                "unallocated_amount": 125.50,
                "deposit": 125.50,
                "withdrawal": 0,
                "date": "2026-10-02",
            }
        )

        invoice = frappe._dict(
            {
                "name": "SINV-TEST-0004",
                "payment_terms_template": None,
                "payment_schedule": [],
            }
        )

        payment_entry = MagicMock()
        payment_entry.name = "PE-TEST-0004"

        def get_doc_side_effect(doctype, name=None, *args, **kwargs):
            if isinstance(doctype, dict):
                return payment_entry
            if doctype == "SEPA Payment Bordereau":
                return bordereau
            if doctype == "Bank Transaction":
                return bank_transaction
            if doctype == "Sales Invoice":
                return invoice
            raise AssertionError(f"Unexpected frappe.get_doc call: {doctype}, {name}")

        def get_value_side_effect(doctype, filters=None, fieldname=None, *args, **kwargs):
            if doctype == "SEPA Payment Bordereau Line":
                return sepa_line
            if doctype == "Bank Account":
                return "Test Bank GL - TC"
            raise AssertionError(
                f"Unexpected frappe.db.get_value call: {doctype}, {filters}, {fieldname}"
            )

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
            patch("frappe.db.set_value"),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_payment_entry_account_fields",
                return_value=("Receive", {}),
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_remittance_info",
                return_value="SEPA test",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_invoice_reference",
                return_value="SINV-TEST-0004",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "sync_invoice_sepa_bordereau_link"
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "update_bordereau_status"
            ),
            patch("frappe.msgprint"),
            patch(
                "erpnext.accounts.doctype.bank_reconciliation_tool."
                "bank_reconciliation_tool.reconcile_vouchers"
            ) as reconcile_vouchers,
        ):
            result = reconcile_bank_transaction_to_sepa_line(
                bank_transaction.name,
                "TEST-20261002-ABCDEF06",
            )

        self.assertEqual(result, payment_entry.name)
        payment_entry.insert.assert_called_once_with()
        payment_entry.submit.assert_called_once_with()
        reconcile_vouchers.assert_called_once()

    def test_reconciliation_rejects_wrong_bank_transaction_direction(self):
        sepa_line = frappe._dict(
            {
                "name": "SEPA-LINE-TEST-0003",
                "parent": "SEPA-BORDEREAU-TEST-0003",
                "invoice": "PINV-TEST-0003",
                "invoice_type": "Purchase Invoice",
                "party": "Test Supplier",
                "party_type": "Supplier",
                "amount": 125.50,
                "mandate": None,
                "status": "Pending",
            }
        )

        bordereau = frappe._dict(
            {
                "name": "SEPA-BORDEREAU-TEST-0003",
                "company": "Test Company",
                "bank_account": "Test Company Bank",
                "payment_type": "Credit",
            }
        )

        # Credit / Pay is an outgoing SEPA payment, but this transaction
        # is deliberately an incoming bank deposit.
        bank_transaction = frappe._dict(
            {
                "name": "BANK-TRANSACTION-TEST-0003",
                "unallocated_amount": 125.50,
                "deposit": 125.50,
                "withdrawal": 0,
                "date": "2026-10-02",
            }
        )

        def get_doc_side_effect(doctype, name=None, *args, **kwargs):
            if isinstance(doctype, dict):
                raise AssertionError(
                    "Payment Entry must not be created for the wrong bank transaction direction"
                )
            if doctype == "SEPA Payment Bordereau":
                return bordereau
            if doctype == "Bank Transaction":
                return bank_transaction
            raise AssertionError(f"Unexpected frappe.get_doc call: {doctype}, {name}")

        def get_value_side_effect(doctype, filters=None, fieldname=None, *args, **kwargs):
            if doctype == "SEPA Payment Bordereau Line":
                return sepa_line
            if doctype == "Bank Account":
                return "Test Bank GL - TC"
            raise AssertionError(
                f"Unexpected frappe.db.get_value call: {doctype}, {filters}, {fieldname}"
            )

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
            patch("frappe.db.set_value") as set_value,
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_payment_entry_account_fields",
                return_value=("Pay", {}),
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_remittance_info",
                return_value="SEPA test",
            ),
            patch(
                "erpnext_france.regional.france.sepa_utils."
                "get_sepa_line_invoice_reference",
                return_value="PINV-TEST-0003",
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                reconcile_bank_transaction_to_sepa_line(
                    bank_transaction.name,
                    "TEST-20261002-ABCDEF05",
                )

        set_value.assert_not_called()
