import unittest
from types import SimpleNamespace
from unittest.mock import patch

from erpnext_france.controllers.fiscal_information import (
        FISCAL_INVOICE_MENTION_FIELD,
        FISCAL_LEGAL_REFERENCE_FIELD,
        sync_sales_invoice_fiscal_information,
)


LEGAL_REFERENCE = "Article 294 CGI ; Article L.211-7 CIBS"
INVOICE_MENTION = (
        "Exonération de TVA en application des articles 294 du Code général "
        "des impôts (CGI) et L211-7 du Code des Impositions sur les Biens "
        "et Services (CIBS)"
)


class FakeSalesInvoice(SimpleNamespace):
        def set(self, fieldname, value):
                setattr(self, fieldname, value)


class TestFiscalInformation(unittest.TestCase):
        @patch(
                "erpnext_france.controllers.fiscal_information."
                "get_tax_category_fiscal_information"
        )
        def test_sales_invoice_snapshots_tax_category_fiscal_information(self, get_metadata):
                get_metadata.return_value = {
                        FISCAL_LEGAL_REFERENCE_FIELD: LEGAL_REFERENCE,
                        FISCAL_INVOICE_MENTION_FIELD: INVOICE_MENTION,
                }

                invoice = FakeSalesInvoice(
                        docstatus=0,
                        tax_category="Vente Biens - Métropole",
                )

                sync_sales_invoice_fiscal_information(invoice)

                get_metadata.assert_called_once_with("Vente Biens - Métropole")
                self.assertEqual(
                        getattr(invoice, FISCAL_LEGAL_REFERENCE_FIELD),
                        LEGAL_REFERENCE,
                )
                self.assertEqual(
                        getattr(invoice, FISCAL_INVOICE_MENTION_FIELD),
                        INVOICE_MENTION,
                )

        @patch(
                "erpnext_france.controllers.fiscal_information."
                "get_tax_category_fiscal_information"
        )
        def test_sales_invoice_clears_fiscal_information_without_tax_category(
                self, get_metadata
        ):
                get_metadata.return_value = None

                invoice = FakeSalesInvoice(
                        docstatus=0,
                        tax_category=None,
                        custom_france_fiscal_legal_reference="Ancienne référence",
                        custom_france_fiscal_invoice_mention="Ancienne mention",
                )

                sync_sales_invoice_fiscal_information(invoice)

                get_metadata.assert_called_once_with(None)
                self.assertIsNone(
                        getattr(invoice, FISCAL_LEGAL_REFERENCE_FIELD)
                )
                self.assertIsNone(
                        getattr(invoice, FISCAL_INVOICE_MENTION_FIELD)
                )

        @patch(
                "erpnext_france.controllers.fiscal_information."
                "get_tax_category_fiscal_information"
        )
        def test_submitted_sales_invoice_is_not_resynchronized(self, get_metadata):
                invoice = FakeSalesInvoice(
                        docstatus=1,
                        tax_category="Vente Biens - Métropole",
                        custom_france_fiscal_legal_reference=LEGAL_REFERENCE,
                        custom_france_fiscal_invoice_mention=INVOICE_MENTION,
                )

                sync_sales_invoice_fiscal_information(invoice)

                get_metadata.assert_not_called()
                self.assertEqual(
                        getattr(invoice, FISCAL_LEGAL_REFERENCE_FIELD),
                        LEGAL_REFERENCE,
                )
                self.assertEqual(
                        getattr(invoice, FISCAL_INVOICE_MENTION_FIELD),
                        INVOICE_MENTION,
                )


if __name__ == "__main__":
        unittest.main()
