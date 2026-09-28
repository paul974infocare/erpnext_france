import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

import frappe

from erpnext_france import setup
from erpnext_france.patches.v16_0 import enable_french_accounting_settings


class TestFrenchAccountingSettings(unittest.TestCase):
	def test_enables_immutable_ledger_and_disables_ledger_entry_deletion(self):
		with patch.object(setup.frappe.db, "set_single_value") as set_single_value:
			setup.set_french_accounting_settings()

		set_single_value.assert_has_calls(
			[
				call("Accounts Settings", "enable_immutable_ledger", 1),
				call("Accounts Settings", "delete_linked_ledger_entries", 0),
			]
		)

	def test_is_idempotent(self):
		settings = {
			"enable_immutable_ledger": frappe.db.get_single_value(
				"Accounts Settings", "enable_immutable_ledger"
			),
			"delete_linked_ledger_entries": frappe.db.get_single_value(
				"Accounts Settings", "delete_linked_ledger_entries"
			),
		}

		try:
			frappe.db.set_single_value("Accounts Settings", "enable_immutable_ledger", 0)
			frappe.db.set_single_value("Accounts Settings", "delete_linked_ledger_entries", 1)

			setup.set_french_accounting_settings()
			self.assertEqual(
				frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"),
				1,
			)
			self.assertEqual(
				frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"),
				0,
			)

			setup.set_french_accounting_settings()
			self.assertEqual(
				frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"),
				1,
			)
			self.assertEqual(
				frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"),
				0,
			)
		finally:
			for fieldname, value in settings.items():
				frappe.db.set_single_value("Accounts Settings", fieldname, value)

	def test_patch_applies_settings_when_supported_company_exists(self):
		with (
			patch.object(
				enable_french_accounting_settings.frappe,
				"get_all",
				return_value=[SimpleNamespace(name="French Company")],
			) as get_all,
			patch.object(
				enable_french_accounting_settings,
				"set_french_accounting_settings",
			) as set_settings,
		):
			enable_french_accounting_settings.execute()

		get_all.assert_called_once_with(
			"Company",
			filters={"country": ["in", setup.SUPPORTED_ACCOUNTING_COUNTRIES]},
			fields=["name"],
			limit=1,
		)
		set_settings.assert_called_once_with()

	def test_patch_has_no_effect_outside_supported_company_scope(self):
		with (
			patch.object(enable_french_accounting_settings.frappe, "get_all", return_value=[]),
			patch.object(
				enable_french_accounting_settings,
				"set_french_accounting_settings",
			) as set_settings,
		):
			enable_french_accounting_settings.execute()

		set_settings.assert_not_called()


if __name__ == "__main__":
	unittest.main()