import unittest
from unittest.mock import MagicMock, patch

from erpnext_france.utils import create_tax_template


class TestReunionTaxRules(unittest.TestCase):
	COMPANY = "Réunion Test"

	def setUp(self):
		self.dataset = {
			"tax_rules": [
				{
					"tax_type": "Sales",
					"tax_category": "Vente Biens - Métropole",
					"tax_template": "Export Biens Réunion vers Métropole",
				},
				{
					"tax_type": "Sales",
					"tax_category": "Vente Services - Métropole",
					"tax_template": "Services Réunion vers Métropole - TVA 20%",
				},
				{
					"tax_type": "Purchase",
					"tax_category": "Achat Services - Métropole",
					"tax_template": "Services Métropole vers Réunion - TVA 8.5%",
				},
			]
		}
		self.templates = {
			("Sales", "Vente Biens - Métropole"): {
				"name": "Export Biens Réunion vers Métropole - Réunion Test",
				"title": "Export Biens Réunion vers Métropole",
			},
			("Sales", "Vente Services - Métropole"): {
				"name": "Services Réunion vers Métropole - TVA 20% - Réunion Test",
				"title": "Services Réunion vers Métropole - TVA 20%",
			},
			("Purchase", "Achat Services - Métropole"): {
				"name": "Services Métropole vers Réunion - TVA 8.5% - Réunion Test",
				"title": "Services Métropole vers Réunion - TVA 8.5%",
			},
		}

	def _get_templates(self, doctype, filters, fields):
		tax_type = "Sales" if doctype.startswith("Sales") else "Purchase"
		return [self.templates[(tax_type, filters["tax_category"])] ]

	def test_creates_expected_rules_idempotently(self):
		db = MagicMock()
		db.exists.side_effect = [False, False, False, True, True, True]
		created_docs = []

		def get_doc(values):
			doc = MagicMock()
			doc.values = values
			created_docs.append(doc)
			return doc

		with patch.object(create_tax_template.frappe, "db", db), patch.object(
			create_tax_template.frappe, "get_all", side_effect=self._get_templates
		), patch.object(create_tax_template.frappe, "get_doc", side_effect=get_doc):
			create_tax_template.create_tax_rules(self.COMPANY, self.dataset)
			create_tax_template.create_tax_rules(self.COMPANY, self.dataset)

		self.assertEqual(len(created_docs), 3)
		self.assertEqual(
			[doc.values["tax_category"] for doc in created_docs],
			[
				"Vente Biens - Métropole",
				"Vente Services - Métropole",
				"Achat Services - Métropole",
			],
		)
		self.assertEqual(created_docs[0].values["sales_tax_template"], self.templates[("Sales", "Vente Biens - Métropole")]["name"])
		self.assertEqual(created_docs[1].values["sales_tax_template"], self.templates[("Sales", "Vente Services - Métropole")]["name"])
		self.assertEqual(created_docs[2].values["purchase_tax_template"], self.templates[("Purchase", "Achat Services - Métropole")]["name"])

	def test_skips_ambiguous_template_relation(self):
		db = MagicMock()
		created_docs = []

		with patch.object(create_tax_template.frappe, "db", db), patch.object(
			create_tax_template.frappe,
			"get_all",
			return_value=[self.templates[("Sales", "Vente Biens - Métropole")]] * 2,
		), patch.object(create_tax_template.frappe, "get_doc", side_effect=created_docs.append):
			create_tax_template.create_tax_rules(self.COMPANY, {"tax_rules": [self.dataset["tax_rules"][0]]})

		self.assertEqual(created_docs, [])

	def test_skips_domestic_ambiguity_and_goods_import(self):
		rules = {
			"tax_rules": [
				{
					"tax_type": "Sales",
					"tax_category": "Vente Domestique",
					"tax_template": "TVA 8.5% Collectée",
				},
				{
					"tax_type": "Purchase",
					"tax_category": "Achat Domestique",
					"tax_template": "TVA 8.5% Déductible",
				},
				{
					"tax_type": "Purchase",
					"tax_category": "Achat Biens - Métropole",
					"tax_template": "Import TVA",
				},
			]
		}
		db = MagicMock()
		created_docs = []

		def get_templates(doctype, filters, fields):
			if filters["tax_category"] == "Achat Biens - Métropole":
				return []
			return [{"name": "ambiguous", "title": "template"}] * 2

		with patch.object(create_tax_template.frappe, "db", db), patch.object(
			create_tax_template.frappe, "get_all", side_effect=get_templates
		), patch.object(create_tax_template.frappe, "get_doc", side_effect=created_docs.append):
			create_tax_template.create_tax_rules(self.COMPANY, rules)

		self.assertEqual(created_docs, [])

	def test_dataset_does_not_configure_domestic_or_goods_import_rules(self):
		configured_categories = {rule["tax_category"] for rule in self.dataset["tax_rules"]}

		self.assertNotIn("Vente Domestique", configured_categories)
		self.assertNotIn("Achat Domestique", configured_categories)
		self.assertNotIn("Achat Biens - Métropole", configured_categories)


if __name__ == "__main__":
	unittest.main()