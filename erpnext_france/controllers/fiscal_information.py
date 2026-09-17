# Copyright (c) 2026 SCOPEN
# For license information, please see license.txt

import frappe


FISCAL_LEGAL_REFERENCE_FIELD = "custom_france_fiscal_legal_reference"
FISCAL_INVOICE_MENTION_FIELD = "custom_france_fiscal_invoice_mention"


def get_tax_category_fiscal_information(tax_category):
        if not tax_category:
                return None

        return frappe.db.get_value(
                "Tax Category",
                tax_category,
                [
                        FISCAL_LEGAL_REFERENCE_FIELD,
                        FISCAL_INVOICE_MENTION_FIELD,
                ],
                as_dict=True,
        )


def sync_sales_invoice_fiscal_information(doc, method=None):
        """Snapshot fiscal metadata from the Tax Category onto a draft Sales Invoice."""
        if doc.docstatus != 0:
                return

        legal_reference = None
        invoice_mention = None

        metadata = get_tax_category_fiscal_information(doc.tax_category)

        if metadata:
                legal_reference = metadata.get(FISCAL_LEGAL_REFERENCE_FIELD)
                invoice_mention = metadata.get(FISCAL_INVOICE_MENTION_FIELD)

        doc.set(FISCAL_LEGAL_REFERENCE_FIELD, legal_reference)
        doc.set(FISCAL_INVOICE_MENTION_FIELD, invoice_mention)
