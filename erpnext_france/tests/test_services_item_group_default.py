import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from erpnext_france import setup
from erpnext_france.patches.v16_0 import configure_services_item_group_default


class TestConfigureFrenchCompanyDefaults(unittest.TestCase):
	def setUp(self):
		self.company = SimpleNamespace(name="French Company", country="France")
		self.income_account = "706 - Prestations de services - FC"
		self.item_group = MagicMock(item_group_defaults=[])

	def configure(self, *, account=None, item_group_exists=True, defaults=None):
		self.item_group.item_group_defaults = defaults or []
		db = MagicMock()
		db.get_value.return_value = account
		db.exists.return_value = item_group_exists

		with (
			patch.object(setup.frappe, "db", db),
			patch.object(setup.frappe, "get_doc", return_value=self.item_group),
		):
			setup.configure_french_company_defaults(self.company)

		return db

	def test_creates_services_default_for_supported_company(self):
		db = self.configure(account=self.income_account)

		db.get_value.assert_called_once_with(
			"Account",
			{"account_number": "706", "company": self.company.name, "is_group": 0},
			"name",
		)
		self.item_group.append.assert_called_once_with(
			"item_group_defaults",
			{"company": self.company.name, "income_account": self.income_account},
		)
		self.item_group.save.assert_called_once_with(ignore_permissions=True)

	def test_second_execution_does_not_duplicate_default(self):
		default = SimpleNamespace(company=self.company.name, income_account=self.income_account)
		self.configure(account=self.income_account, defaults=[default])

		self.item_group.append.assert_not_called()
		self.item_group.save.assert_not_called()

	def test_existing_correct_default_is_unchanged(self):
		default = SimpleNamespace(company=self.company.name, income_account=self.income_account)
		self.configure(account=self.income_account, defaults=[default])

		self.item_group.save.assert_not_called()

	def test_existing_other_default_is_unchanged(self):
		default = SimpleNamespace(
			company=self.company.name,
			income_account="7071 - Ventes de produits - FC",
		)
		self.configure(account=self.income_account, defaults=[default])

		self.item_group.append.assert_not_called()
		self.item_group.save.assert_not_called()

	def test_company_outside_supported_scope_is_ignored(self):
		company = SimpleNamespace(name="Foreign Company", country="Belgium")

		with patch.object(setup.frappe, "db") as db:
			setup.configure_french_company_defaults(company)

		db.get_value.assert_not_called()

	def test_missing_income_account_is_safe(self):
		db = self.configure(account=None)

		db.exists.assert_not_called()
		self.item_group.append.assert_not_called()
		self.item_group.save.assert_not_called()

	def test_missing_services_group_is_safe(self):
		db = self.configure(account=self.income_account, item_group_exists=False)

		self.item_group.append.assert_not_called()
		self.item_group.save.assert_not_called()


class TestConfigureServicesItemGroupDefaultPatch(unittest.TestCase):
	def test_patch_uses_shared_provisioning_function_and_is_repeatable(self):
		companies = [SimpleNamespace(name="French Company", country="France")]

		with (
			patch.object(
				configure_services_item_group_default.frappe,
				"get_all",
				return_value=companies,
			) as get_all,
			patch.object(
				configure_services_item_group_default,
				"configure_french_company_defaults",
			) as configure_defaults,
		):
			configure_services_item_group_default.execute()
			configure_services_item_group_default.execute()

		get_all.assert_called_with(
			"Company",
			filters={"country": ["in", setup.SUPPORTED_ACCOUNTING_COUNTRIES]},
			fields=["name", "country"],
		)
		self.assertEqual(configure_defaults.call_count, 2)
		configure_defaults.assert_any_call(companies[0])


if __name__ == "__main__":
	unittest.main()
