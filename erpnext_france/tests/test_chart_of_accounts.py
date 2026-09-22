import json
from pathlib import Path
import unittest


CHART_OF_ACCOUNTS_PATH = (
	Path(__file__).parents[1]
	/ "regional"
	/ "france"
	/ "chart_of_accounts"
	/ "fr_plan2025_comptable_general_avec_code.json"
)


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

		self.assertEqual(
			account_4091,
			{"account_number": "4091", "account_type": "Payable", "root_type": "Asset"},
		)
		self.assertEqual(
			account_4191,
			{"account_number": "4191", "account_type": "Receivable", "root_type": "Liability"},
		)


if __name__ == "__main__":
	unittest.main()