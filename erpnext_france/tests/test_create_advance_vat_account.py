import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from erpnext_france.patches.v16_0 import create_advance_vat_account


class TestCreateAdvanceVatAccount(unittest.TestCase):
	def setUp(self):
		self.company = SimpleNamespace(name="French Company")
		self.parent = "4458-Taxes sur le chiffre d'affaires à régulariser ou en attente - FC"
		self.account = SimpleNamespace(
			name="44588 - TVA sur acomptes à régulariser - FC",
			parent_account=self.parent,
			root_type="Asset",
			account_type="Tax",
			is_group=0,
		)

	def test_creates_account_under_asset_parent(self):
		new_account = MagicMock()
		db = MagicMock()
		db.get_value.side_effect = [self.parent, None]

		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[self.company]),
			patch.object(create_advance_vat_account.frappe, "db", db),
			patch.object(create_advance_vat_account.frappe, "new_doc", return_value=new_account),
		):
			create_advance_vat_account.execute()

		db.get_value.assert_any_call(
			"Account",
			{
				"account_name": create_advance_vat_account.PARENT_ACCOUNT_NAME,
				"company": self.company.name,
				"root_type": "Asset",
				"is_group": 1,
			},
			"name",
		)
		new_account.update.assert_called_once_with(
			{
				"account_name": "TVA sur acomptes à régulariser",
				"account_number": "44588",
				"account_type": "Tax",
				"company": self.company.name,
				"parent_account": self.parent,
			}
		)
		new_account.insert.assert_called_once_with(ignore_permissions=True)

	def test_second_pass_is_idempotent(self):
		db = MagicMock()
		db.get_value.side_effect = [self.parent, self.account]

		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[self.company]),
			patch.object(create_advance_vat_account.frappe, "db", db),
			patch.object(create_advance_vat_account.frappe, "new_doc") as new_doc,
		):
			create_advance_vat_account.execute()

		new_doc.assert_not_called()
		db.get_value.assert_any_call(
			"Account",
			{
				"account_name": create_advance_vat_account.PARENT_ACCOUNT_NAME,
				"company": self.company.name,
				"root_type": "Asset",
				"is_group": 1,
			},
			"name",
		)

	def test_skips_when_asset_parent_is_missing(self):
		db = MagicMock()
		db.get_value.return_value = None

		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[self.company]),
			patch.object(create_advance_vat_account.frappe, "db", db),
			patch.object(create_advance_vat_account.frappe, "new_doc") as new_doc,
		):
			create_advance_vat_account.execute()

		new_doc.assert_not_called()

	def test_existing_compatible_account_is_unchanged(self):
		db = MagicMock()
		db.get_value.side_effect = [self.parent, self.account]

		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[self.company]),
			patch.object(create_advance_vat_account.frappe, "db", db),
			patch.object(create_advance_vat_account.frappe, "new_doc") as new_doc,
		):
			create_advance_vat_account.execute()

		new_doc.assert_not_called()

	def test_existing_incompatible_account_is_logged_and_unchanged(self):
		incompatible_account = SimpleNamespace(
			name=self.account.name,
			parent_account="4458 - TVA à régulariser - Liability FC",
			root_type="Liability",
			account_type="Tax",
			is_group=0,
		)
		db = MagicMock()
		db.get_value.side_effect = [self.parent, incompatible_account]

		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[self.company]),
			patch.object(create_advance_vat_account.frappe, "db", db),
			patch.object(create_advance_vat_account.frappe, "new_doc") as new_doc,
			patch.object(create_advance_vat_account.frappe, "log_error") as log_error,
		):
			create_advance_vat_account.execute()

		new_doc.assert_not_called()
		log_error.assert_called_once()
		self.assertIn("44588", log_error.call_args.kwargs["message"])

	def test_company_outside_regional_scope_is_ignored(self):
		with (
			patch.object(create_advance_vat_account.frappe, "get_all", return_value=[]) as get_all,
			patch.object(create_advance_vat_account.frappe, "new_doc") as new_doc,
		):
			create_advance_vat_account.execute()

		get_all.assert_called_once_with(
			"Company",
			filters={"country": ["in", create_advance_vat_account.SUPPORTED_COUNTRIES]},
			fields=["name"],
		)
		new_doc.assert_not_called()


if __name__ == "__main__":
	unittest.main()
