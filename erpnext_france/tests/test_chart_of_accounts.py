import json
import unittest
from pathlib import Path

CHART_OF_ACCOUNTS_PATH = (
	Path(__file__).parents[1]
	/ "regional"
	/ "france"
	/ "chart_of_accounts"
	/ "fr_plan2025_comptable_general_avec_code.json"
)
CUSTOM_FIELDS_PATH = Path(__file__).parents[1] / "fixtures" / "custom_field.json"


class TestChartOfAccounts(unittest.TestCase):
	def test_advance_accounts_have_expected_types(self):
		with CHART_OF_ACCOUNTS_PATH.open(encoding="utf-8") as chart_file:
			chart = json.load(chart_file)

		def find_account(node, account_number, root_type=None):
			if not isinstance(node, dict):
				return None

			root_type = node.get("root_type", root_type)
			if node.get("account_number") == account_number:
				return {**node, "root_type": root_type}

			for child in node.values():
				account = find_account(child, account_number, root_type)
				if account:
					return account

			return None

		account_4091 = find_account(chart["tree"], "4091")
		account_4191 = find_account(chart["tree"], "4191")
		account_44588 = find_account(chart["tree"], "44588")

		self.assertEqual(
			account_4091,
			{"account_number": "4091", "account_type": "Payable", "root_type": "Asset"},
		)
		self.assertEqual(
			account_4191,
			{"account_number": "4191", "account_type": "Receivable", "root_type": "Liability"},
		)
		self.assertEqual(
			account_44588,
			{"account_number": "44588", "account_type": "Tax", "root_type": "Asset"},
		)

	def test_default_advance_vat_account_custom_field(self):
		with CUSTOM_FIELDS_PATH.open(encoding="utf-8") as custom_fields_file:
			custom_fields = json.load(custom_fields_file)

		field = next(
			field
			for field in custom_fields
			if field.get("name") == "Company-default_advance_vat_account"
		)

		self.assertEqual(field["dt"], "Company")
		self.assertEqual(field["fieldname"], "default_advance_vat_account")
		self.assertEqual(field["fieldtype"], "Link")
		self.assertEqual(field["options"], "Account")
		self.assertEqual(field["label"], "Default Advance VAT Account")
		self.assertEqual(field["reqd"], 0)
		self.assertEqual(
			json.loads(field["link_filters"]),
			[
				["Account", "company", "=", "eval:doc.name"],
				["Account", "is_group", "=", 0],
				["Account", "account_type", "=", "Tax"],
			],
		)


if __name__ == "__main__":
	unittest.main()
