import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from erpnext_france.patches.v16_0 import move_vat_due_accounts_to_liability


class TestMoveVatDueAccountsToLiability(unittest.TestCase):
	def setUp(self):
		self.company = SimpleNamespace(name="French Company")
		self.target_parent = "445-État - Taxes sur le chiffre d'affaires 1 - FC"

	def _account(self, number, root_type="Asset", parent_account="445 - Asset - FC"):
		account = MagicMock()
		account.name = f"{number} - VAT - FC"
		account.account_number = number
		account.parent_account = parent_account
		account.root_type = root_type
		account.account_type = "Tax"
		account.is_group = 0
		return account

	def test_moves_4452_and_4453_to_liability_parent(self):
		account_4452 = self._account("4452")
		account_4453 = self._account("4453")

		db = MagicMock()
		db.get_value.side_effect = [
			self.target_parent,
			account_4452.name,
			account_4453.name,
		]

		with (
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_all",
				return_value=[self.company],
			),
			patch.object(move_vat_due_accounts_to_liability.frappe, "db", db),
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_doc",
				side_effect=[account_4452, account_4453],
			),
		):
			move_vat_due_accounts_to_liability.execute()

		self.assertEqual(account_4452.parent_account, self.target_parent)
		self.assertEqual(account_4453.parent_account, self.target_parent)
		account_4452.save.assert_called_once_with(ignore_permissions=True)
		account_4453.save.assert_called_once_with(ignore_permissions=True)

	def test_second_pass_is_idempotent(self):
		account_4452 = self._account(
			"4452",
			root_type="Liability",
			parent_account=self.target_parent,
		)
		account_4453 = self._account(
			"4453",
			root_type="Liability",
			parent_account=self.target_parent,
		)

		db = MagicMock()
		db.get_value.side_effect = [
			self.target_parent,
			account_4452.name,
			account_4453.name,
		]

		with (
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_all",
				return_value=[self.company],
			),
			patch.object(move_vat_due_accounts_to_liability.frappe, "db", db),
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_doc",
				side_effect=[account_4452, account_4453],
			),
		):
			move_vat_due_accounts_to_liability.execute()

		account_4452.save.assert_not_called()
		account_4453.save.assert_not_called()

	def test_missing_liability_branch_is_logged_and_skipped(self):
		db = MagicMock()
		db.get_value.return_value = None

		with (
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_all",
				return_value=[self.company],
			),
			patch.object(move_vat_due_accounts_to_liability.frappe, "db", db),
			patch.object(move_vat_due_accounts_to_liability.frappe, "get_doc") as get_doc,
			patch.object(move_vat_due_accounts_to_liability.frappe, "log_error") as log_error,
		):
			move_vat_due_accounts_to_liability.execute()

		get_doc.assert_not_called()
		log_error.assert_called_once()

	def test_missing_vat_due_account_is_ignored(self):
		db = MagicMock()
		db.get_value.side_effect = [
			self.target_parent,
			None,
			None,
		]

		with (
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_all",
				return_value=[self.company],
			),
			patch.object(move_vat_due_accounts_to_liability.frappe, "db", db),
			patch.object(move_vat_due_accounts_to_liability.frappe, "get_doc") as get_doc,
		):
			move_vat_due_accounts_to_liability.execute()

		get_doc.assert_not_called()

	def test_company_outside_regional_scope_is_ignored(self):
		with (
			patch.object(
				move_vat_due_accounts_to_liability.frappe,
				"get_all",
				return_value=[],
			) as get_all,
			patch.object(move_vat_due_accounts_to_liability.frappe, "get_doc") as get_doc,
		):
			move_vat_due_accounts_to_liability.execute()

		get_all.assert_called_once_with(
			"Company",
			filters={
				"country": [
					"in",
					move_vat_due_accounts_to_liability.SUPPORTED_COUNTRIES,
				]
			},
			fields=["name"],
		)
		get_doc.assert_not_called()


if __name__ == "__main__":
	unittest.main()
