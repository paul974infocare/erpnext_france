import json
from pathlib import Path
import unittest


DATASET_PATH = Path(__file__).parents[1] / "data" / "country_wise_tax.json"


class TestCountryWiseTax(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
                with DATASET_PATH.open(encoding="utf-8") as dataset_file:
                        cls.dataset = json.load(dataset_file)

        def test_chart_identifier_is_canonical(self):
                self.assertIn("Plan Comptable Général", self.dataset["France"]["chart_of_accounts"])
                self.assertNotIn(
                        "France - Plan Comptable General 2025 avec code",
                        self.dataset["France"]["chart_of_accounts"],
                )

        def test_reunion_dataset_scope(self):
                reunion = self.dataset["Réunion"]
                chart = reunion["chart_of_accounts"]["Plan Comptable Général"]

                self.assertEqual(
                        reunion["tax_categories"],
                        [
                                "Vente Domestique",
                                "Achat Domestique",
                                "Vente Biens - Métropole",
                                "Achat Biens - Métropole",
                                "Vente Services - Métropole",
                                "Achat Services - Métropole",
                        ],
                )
                self.assertEqual(
                        [template["title"] for template in chart["sales_tax_templates"]],
                        [
                                "TVA 8.5% Collectée",
                                "TVA 2.1% Collectée",
                                "Export Biens Réunion vers Métropole",
                                "Services Réunion vers Métropole - TVA 20%",
                        ],
                )
                self.assertEqual(
                        [template["title"] for template in chart["purchase_tax_templates"]],
                        [
                                "TVA 8.5% Déductible",
                                "TVA 2.1% Déductible",
                                "Import Biens Métropole vers Réunion - TVA 8.5%",
                                "Services Métropole vers Réunion - TVA 8.5%",
                        ],
                )
                self.assertEqual(
                        [template["title"] for template in chart["item_tax_templates"]],
                        [
                                "TVA 8.5% Déductible - Achat",
                                "TVA 2.1% Déductible - Achat",
                                "TVA 8.5% Collectée - Vente",
                                "TVA 2.1% Collectée - Vente",
                        ],
                )

        def test_reunion_domestic_rates_and_accounts(self):
                chart = self.dataset["Réunion"]["chart_of_accounts"]["Plan Comptable Général"]
                expected = {
                        "TVA 8.5% Collectée": ("445785", "Liability", 8.5),
                        "TVA 2.1% Collectée": ("445721", "Liability", 2.1),
                        "TVA 8.5% Déductible": ("445685", "Asset", 8.5),
                        "TVA 2.1% Déductible": ("445621", "Asset", 2.1),
                }

                templates = (
                        chart["sales_tax_templates"][:2]
                        + chart["purchase_tax_templates"][:2]
                )

                for template in templates:
                        account = template["taxes"][0]["account_head"]
                        self.assertEqual(
                                (
                                        account["account_number"],
                                        account["root_type"],
                                        account["tax_rate"],
                                ),
                                expected[template["title"]],
                        )

        def test_reunion_goods_sale_to_metropole_has_fiscal_metadata(self):
                metadata = self.dataset["Réunion"]["france_fiscal_metadata"]

                self.assertEqual(
                        set(metadata),
                        {"Vente Biens - Métropole"},
                )
                self.assertEqual(
                        metadata["Vente Biens - Métropole"]["legal_reference"],
                        "Article 294 CGI ; Article L.211-7 CIBS",
                )
                self.assertEqual(
                        metadata["Vente Biens - Métropole"]["invoice_mention"],
                        "Exonération de TVA en application des articles 294 du Code général des impôts (CGI) et L211-7 du Code des Impositions sur les Biens et Services (CIBS)",
                )

        def test_reunion_goods_sale_to_metropole_is_tax_free_template(self):
                chart = self.dataset["Réunion"]["chart_of_accounts"]["Plan Comptable Général"]

                template = next(
                        template
                        for template in chart["sales_tax_templates"]
                        if template["title"] == "Export Biens Réunion vers Métropole"
                )

                self.assertEqual(template["tax_category"], "Vente Biens - Métropole")
                self.assertEqual(template["taxes"], [])

        def test_reunion_goods_import_from_metropole_uses_import_vat_accounts(self):
                chart = self.dataset["Réunion"]["chart_of_accounts"]["Plan Comptable Général"]

                template = next(
                        template
                        for template in chart["purchase_tax_templates"]
                        if template["title"] == "Import Biens Métropole vers Réunion - TVA 8.5%"
                )

                self.assertEqual(template["tax_category"], "Achat Biens - Métropole")
                self.assertEqual(len(template["taxes"]), 2)

                import_vat, deductible_vat = template["taxes"]

                self.assertEqual(
                        (
                                import_vat["account_head"]["account_number"],
                                import_vat["account_head"]["root_type"],
                                import_vat["rate"],
                                import_vat["add_deduct_tax"],
                        ),
                        ("4453", "Asset", 8.5, "Deduct"),
                )

                self.assertEqual(
                        (
                                deductible_vat["account_head"]["account_number"],
                                deductible_vat["account_head"]["root_type"],
                                deductible_vat["rate"],
                                deductible_vat["add_deduct_tax"],
                        ),
                        ("445685", "Asset", 8.5, "Add"),
                )

        def test_reunion_service_sale_to_metropole_uses_20_percent_vat(self):
                chart = self.dataset["Réunion"]["chart_of_accounts"]["Plan Comptable Général"]

                template = next(
                        template
                        for template in chart["sales_tax_templates"]
                        if template["title"] == "Services Réunion vers Métropole - TVA 20%"
                )

                self.assertEqual(template["tax_category"], "Vente Services - Métropole")
                self.assertEqual(len(template["taxes"]), 1)

                tax = template["taxes"][0]

                self.assertEqual(
                        (
                                tax["account_head"]["account_number"],
                                tax["account_head"]["root_type"],
                                tax["rate"],
                        ),
                        ("445720", "Liability", 20),
                )

        def test_reunion_service_purchase_from_metropole_uses_reunion_vat(self):
                chart = self.dataset["Réunion"]["chart_of_accounts"]["Plan Comptable Général"]

                template = next(
                        template
                        for template in chart["purchase_tax_templates"]
                        if template["title"] == "Services Métropole vers Réunion - TVA 8.5%"
                )

                self.assertEqual(template["tax_category"], "Achat Services - Métropole")
                self.assertEqual(len(template["taxes"]), 1)

                tax = template["taxes"][0]

                self.assertEqual(
                        (
                                tax["account_head"]["account_number"],
                                tax["account_head"]["root_type"],
                                tax["rate"],
                                tax["add_deduct_tax"],
                        ),
                        ("445685", "Asset", 8.5, "Add"),
                )

                self.assertNotEqual(tax["account_head"]["account_number"], "4453")

        def test_reunion_has_no_excluded_tax_configuration(self):
                reunion = self.dataset["Réunion"]
                chart = reunion["chart_of_accounts"]["Plan Comptable Général"]
                serialized = json.dumps(reunion, ensure_ascii=False)

                self.assertNotIn("Achat - EU", reunion["tax_categories"])
                self.assertNotIn("Vente - EU", reunion["tax_categories"])
                self.assertNotIn("Intracommunautaire", serialized)

                for excluded_rate in (10, 5.5, 1.75, 1.05):
                        self.assertNotIn(excluded_rate, self._rates(chart))

        def _rates(self, chart):
                rates = []

                for group in (
                        "sales_tax_templates",
                        "purchase_tax_templates",
                        "item_tax_templates",
                ):
                        for template in chart[group]:
                                for tax in template["taxes"]:
                                        account = tax.get("account_head") or tax.get("tax_type")
                                        rates.append(account["tax_rate"])

                return rates
