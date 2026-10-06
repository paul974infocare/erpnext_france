from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from lxml import etree


PAIN_001_09_NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"


class TestSEPAPain001ISO20022(FrappeTestCase):
    def make_credit_bordereau(self):
        bordereau = frappe.new_doc("SEPA Payment Bordereau")
        bordereau.name = "SEPA-CREDIT-2026-0001"
        bordereau.payment_type = "Credit"
        bordereau.company = "Test Company"
        bordereau.bank_account = "Test Company Bank"
        bordereau.execution_date = "2026-10-05"

        bordereau.append(
            "lines",
            {
                "invoice_type": "Purchase Invoice",
                "invoice": "PINV-TEST-0001",
                "party_type": "Supplier",
                "party": "Test Supplier",
                "amount": 125.50,
                "end_to_end_id": "TEST-20261002-ABCDEF01",
                "status": "Pending",
            },
        )
        bordereau.calculate_total()
        return bordereau

    def test_bordereau_rejects_non_eur_company_bank_account(self):
        bordereau = self.make_credit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test USD Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )

        real_get_value = frappe.db.get_value

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test USD Bank - TC":
                return "USD"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", return_value=company_bank),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")

    def test_bordereau_rejects_default_supplier_bank_account_without_iban(self):
        bordereau = self.make_credit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        supplier_bank = frappe._dict(
            {
                "name": "Test Supplier Bank",
                "iban": None,
                "swift_number": "BNPAFRPPXXX",
            }
        )

        real_get_value = frappe.db.get_value

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if (
                doctype == "Bank Account"
                and args
                and args[0] == "Test Supplier Bank"
                and len(args) > 1
                and args[1] == "iban"
            ):
                return None
            if doctype == "Bank Account":
                return supplier_bank
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", return_value=company_bank),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")

    def test_bordereau_rejects_default_supplier_bank_account_without_bic(self):
        bordereau = self.make_credit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        supplier_bank = frappe._dict(
            {
                "name": "Test Supplier Bank",
                "iban": "FR7611111111111111111111111",
                "swift_number": None,
            }
        )

        real_get_value = frappe.db.get_value

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if doctype == "Bank Account":
                return supplier_bank
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", return_value=company_bank),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")

    def test_pain_001_uses_iso20022_2019_sepa_structure(self):
        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        supplier_bank = frappe._dict(
            {
                "name": "Test Supplier Bank",
                "iban": "FR7611111111111111111111111",
                "swift_number": "BNPAFRPPXXX",
            }
        )

        real_get_value = frappe.db.get_value

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Bank Account":
                return supplier_bank
            return real_get_value(doctype, *args, **kwargs)

        bordereau = self.make_credit_bordereau()

        with (
            patch("frappe.get_doc", return_value=company_bank),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            xml = bordereau.generate_pain_001()

        root = etree.fromstring(xml)

        self.assertEqual(root.nsmap[None], PAIN_001_09_NS)

        ns = {"p": PAIN_001_09_NS}

        self.assertEqual(
            root.xpath("string(.//p:PmtInf/p:PmtMtd)", namespaces=ns),
            "TRF",
        )
        self.assertEqual(
            root.xpath("string(.//p:PmtInf/p:NbOfTxs)", namespaces=ns),
            "1",
        )
        self.assertEqual(
            root.xpath("string(.//p:PmtInf/p:CtrlSum)", namespaces=ns),
            "125.50",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:SvcLvl/p:Cd)",
                namespaces=ns,
            ),
            "SEPA",
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:ReqdExctnDt/p:Dt)",
                namespaces=ns,
            ),
            "2026-10-05",
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:DbtrAgt/p:FinInstnId/p:BICFI)",
                namespaces=ns,
            ),
            "AGRIFRPPXXX",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtTrfTxInf/p:CdtrAgt/p:FinInstnId/p:BICFI)",
                namespaces=ns,
            ),
            "BNPAFRPPXXX",
        )

        self.assertFalse(
            root.xpath(".//p:FinInstnId/p:BIC", namespaces=ns)
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:CdtTrfTxInf/p:PmtId/p:EndToEndId)",
                namespaces=ns,
            ),
            "TEST-20261002-ABCDEF01",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtTrfTxInf/p:Amt/p:InstdAmt/@Ccy)",
                namespaces=ns,
            ),
            "EUR",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtTrfTxInf/p:Amt/p:InstdAmt)",
                namespaces=ns,
            ),
            "125.50",
        )


PAIN_008_08_NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.08"


class TestSEPAPain008ISO20022(FrappeTestCase):
    def make_debit_bordereau(self):
        bordereau = frappe.new_doc("SEPA Payment Bordereau")
        bordereau.name = "SEPA-DEBIT-2026-0001"
        bordereau.payment_type = "Debit"
        bordereau.company = "Test Company"
        bordereau.bank_account = "Test Company Bank"
        bordereau.execution_date = "2026-10-05"

        bordereau.append(
            "lines",
            {
                "invoice_type": "Sales Invoice",
                "invoice": "SINV-TEST-0001",
                "party_type": "Customer",
                "party": "Test Customer",
                "amount": 125.50,
                "mandate": "MANDATE-TEST-0001",
                "end_to_end_id": "TEST-20261002-ABCDEF02",
                "status": "Pending",
            },
        )
        bordereau.calculate_total()
        return bordereau

    def test_bordereau_rejects_active_debit_mandate_without_rum(self):
        bordereau = self.make_debit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "status": "Active",
                "rum": None,
                "signature_date": "2026-09-15",
                "mandate_type": "CORE",
                "sequence_type": "FRST",
                "bank_account": "Test Customer Bank",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")


    def test_bordereau_rejects_active_debit_mandate_without_signature_date(self):
        bordereau = self.make_debit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "status": "Active",
                "rum": "RUM-TEST-0001",
                "signature_date": None,
                "mandate_type": "CORE",
                "sequence_type": "FRST",
                "bank_account": "Test Customer Bank",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")


    def test_bordereau_rejects_debit_mandate_bank_account_without_iban(self):
        bordereau = self.make_debit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        customer_bank = frappe._dict(
            {
                "name": "Test Customer Bank",
                "iban": None,
                "swift_number": "BNPAFRPPXXX",
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "status": "Active",
                "rum": "RUM-TEST-0001",
                "signature_date": "2026-09-15",
                "mandate_type": "CORE",
                "sequence_type": "FRST",
                "bank_account": "Test Customer Bank",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "Bank Account" and args[1] == "Test Customer Bank":
                    return customer_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")


    def test_bordereau_rejects_debit_mandate_bank_account_without_bic(self):
        bordereau = self.make_debit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "account": "Test EUR Bank - TC",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        customer_bank = frappe._dict(
            {
                "name": "Test Customer Bank",
                "iban": "FR7622222222222222222222222",
                "swift_number": None,
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "status": "Active",
                "rum": "RUM-TEST-0001",
                "signature_date": "2026-09-15",
                "mandate_type": "CORE",
                "sequence_type": "FRST",
                "bank_account": "Test Customer Bank",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "Bank Account" and args[1] == "Test Customer Bank":
                    return customer_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Account" and args and args[0] == "Test EUR Bank - TC":
                return "EUR"
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch.object(bordereau, "generate_end_to_end_ids"),
            patch.object(bordereau, "validate_company_bank_account"),
            patch.object(bordereau, "save"),
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.validate_bordereau()

        self.assertEqual(bordereau.status, "Draft")


    def test_pain_008_uses_iso20022_2019_sepa_structure(self):
        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        customer_bank = frappe._dict(
            {
                "name": "Test Customer Bank",
                "iban": "FR7622222222222222222222222",
                "swift_number": "BNPAFRPPXXX",
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "bank_account": "Test Customer Bank",
                "rum": "RUM-TEST-0001",
                "signature_date": "2026-09-15",
                "mandate_type": "CORE",
                "sequence_type": "FRST",
            }
        )

        bordereau = self.make_debit_bordereau()

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "Bank Account" and args[1] == "Test Customer Bank":
                    return customer_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            xml = bordereau.generate_pain_008()

        root = etree.fromstring(xml)

        self.assertEqual(root.nsmap[None], PAIN_008_08_NS)

        ns = {"p": PAIN_008_08_NS}

        self.assertEqual(
            root.xpath("string(.//p:PmtInf/p:PmtMtd)", namespaces=ns),
            "DD",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:SvcLvl/p:Cd)",
                namespaces=ns,
            ),
            "SEPA",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:LclInstrm/p:Cd)",
                namespaces=ns,
            ),
            "CORE",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:SeqTp)",
                namespaces=ns,
            ),
            "FRST",
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:ReqdColltnDt)",
                namespaces=ns,
            ),
            "2026-10-05",
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:CdtrAgt/p:FinInstnId/p:BICFI)",
                namespaces=ns,
            ),
            "AGRIFRPPXXX",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:DrctDbtTxInf/p:DbtrAgt/p:FinInstnId/p:BICFI)",
                namespaces=ns,
            ),
            "BNPAFRPPXXX",
        )
        self.assertFalse(
            root.xpath(".//p:FinInstnId/p:BIC", namespaces=ns)
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:DrctDbtTxInf/p:PmtId/p:EndToEndId)",
                namespaces=ns,
            ),
            "TEST-20261002-ABCDEF02",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:DrctDbtTxInf/p:InstdAmt/@Ccy)",
                namespaces=ns,
            ),
            "EUR",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:DrctDbtTxInf/p:InstdAmt)",
                namespaces=ns,
            ),
            "125.50",
        )

        self.assertEqual(
            root.xpath(
                "string(.//p:MndtRltdInf/p:MndtId)",
                namespaces=ns,
            ),
            "RUM-TEST-0001",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:MndtRltdInf/p:DtOfSgntr)",
                namespaces=ns,
            ),
            "2026-09-15",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id)",
                namespaces=ns,
            ),
            "FR12ZZZ123456",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:SchmeNm/p:Prtry)",
                namespaces=ns,
            ),
            "SEPA",
        )

    def test_pain_008_generates_b2b_direct_debit(self):
        bordereau = self.make_debit_bordereau()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        customer_bank = frappe._dict(
            {
                "name": "Test Customer Bank",
                "iban": "FR7622222222222222222222222",
                "swift_number": "BNPAFRPPXXX",
            }
        )
        mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "bank_account": "Test Customer Bank",
                "rum": "RUM-TEST-B2B-0001",
                "signature_date": "2026-09-15",
                "mandate_type": "B2B",
                "sequence_type": "RCUR",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "Bank Account" and args[1] == "Test Customer Bank":
                    return customer_bank
                if args[0] == "SEPA Mandate" and args[1] == "MANDATE-TEST-0001":
                    return mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            xml = bordereau.generate_pain_008()

        root = etree.fromstring(xml)
        ns = {"p": PAIN_008_08_NS}

        self.assertEqual(root.nsmap[None], PAIN_008_08_NS)
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:LclInstrm/p:Cd)",
                namespaces=ns,
            ),
            "B2B",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:PmtInf/p:PmtTpInf/p:SeqTp)",
                namespaces=ns,
            ),
            "RCUR",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:MndtRltdInf/p:MndtId)",
                namespaces=ns,
            ),
            "RUM-TEST-B2B-0001",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:MndtRltdInf/p:DtOfSgntr)",
                namespaces=ns,
            ),
            "2026-09-15",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id)",
                namespaces=ns,
            ),
            "FR12ZZZ123456",
        )
        self.assertEqual(
            root.xpath(
                "string(.//p:DrctDbtTxInf/p:InstdAmt/@Ccy)",
                namespaces=ns,
            ),
            "EUR",
        )


    def test_pain_008_rejects_mixed_core_and_b2b_mandates(self):
        bordereau = self.make_debit_bordereau()
        bordereau.append(
            "lines",
            {
                "invoice_type": "Sales Invoice",
                "invoice": "SINV-TEST-0002",
                "party_type": "Customer",
                "party": "Test B2B Customer",
                "amount": 75.00,
                "mandate": "MANDATE-TEST-B2B-0001",
                "end_to_end_id": "TEST-20261002-ABCDEF03",
                "status": "Pending",
            },
        )
        bordereau.calculate_total()

        company_bank = frappe._dict(
            {
                "name": "Test Company Bank",
                "iban": "FR7612345678901234567890123",
                "swift_number": "AGRIFRPPXXX",
            }
        )
        customer_bank = frappe._dict(
            {
                "name": "Test Customer Bank",
                "iban": "FR7622222222222222222222222",
                "swift_number": "BNPAFRPPXXX",
            }
        )
        core_mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-0001",
                "bank_account": "Test Customer Bank",
                "rum": "RUM-TEST-0001",
                "signature_date": "2026-09-15",
                "mandate_type": "CORE",
                "sequence_type": "FRST",
            }
        )
        b2b_mandate = frappe._dict(
            {
                "name": "MANDATE-TEST-B2B-0001",
                "bank_account": "Test Customer Bank",
                "rum": "RUM-TEST-B2B-0001",
                "signature_date": "2026-09-16",
                "mandate_type": "B2B",
                "sequence_type": "FRST",
            }
        )

        real_get_doc = frappe.get_doc
        real_get_value = frappe.db.get_value

        def get_doc_side_effect(*args, **kwargs):
            if len(args) >= 2:
                if args[0] == "Bank Account" and args[1] == "Test Company Bank":
                    return company_bank
                if args[0] == "Bank Account" and args[1] == "Test Customer Bank":
                    return customer_bank
                if args[0] == "SEPA Mandate":
                    if args[1] == "MANDATE-TEST-0001":
                        return core_mandate
                    if args[1] == "MANDATE-TEST-B2B-0001":
                        return b2b_mandate
            return real_get_doc(*args, **kwargs)

        def get_value_side_effect(doctype, *args, **kwargs):
            if doctype == "Company":
                return "FR12ZZZ123456"
            return real_get_value(doctype, *args, **kwargs)

        with (
            patch("frappe.get_doc", side_effect=get_doc_side_effect),
            patch("frappe.db.get_value", side_effect=get_value_side_effect),
        ):
            with self.assertRaises(frappe.ValidationError):
                bordereau.generate_pain_008()
