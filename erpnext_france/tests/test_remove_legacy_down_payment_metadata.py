import unittest
from unittest.mock import MagicMock, call, patch

from erpnext_france.patches.v16_0 import remove_legacy_down_payment_metadata


class TestRemoveLegacyDownPaymentMetadata(unittest.TestCase):
	def test_removes_existing_legacy_metadata(self):
		db = MagicMock()
		db.exists.return_value = True

		with patch.object(remove_legacy_down_payment_metadata.frappe, "db", db), patch.object(
			remove_legacy_down_payment_metadata.frappe, "delete_doc"
		) as delete_doc:
			remove_legacy_down_payment_metadata.execute()

		self.assertEqual(
			delete_doc.call_args_list,
			[
				call("Custom Field", name, ignore_permissions=True)
				for name in remove_legacy_down_payment_metadata.LEGACY_CUSTOM_FIELD_NAMES
			]
			+ [
				call("Property Setter", name, ignore_permissions=True)
				for name in remove_legacy_down_payment_metadata.LEGACY_PROPERTY_SETTER_NAMES
			],
		)

	def test_second_pass_is_idempotent(self):
		db = MagicMock()
		db.exists.return_value = False

		with patch.object(remove_legacy_down_payment_metadata.frappe, "db", db), patch.object(
			remove_legacy_down_payment_metadata.frappe, "delete_doc"
		) as delete_doc:
			remove_legacy_down_payment_metadata.execute()
			remove_legacy_down_payment_metadata.execute()

		delete_doc.assert_not_called()

	def test_preserves_current_down_payment_invoice_fields(self):
		legacy_names = set(
			remove_legacy_down_payment_metadata.LEGACY_CUSTOM_FIELD_NAMES
			+ remove_legacy_down_payment_metadata.LEGACY_PROPERTY_SETTER_NAMES
		)

		self.assertNotIn("Payment Entry-down_payment_invoice", legacy_names)
		self.assertNotIn("Payment Entry-down_payment_invoice_amount", legacy_names)


if __name__ == "__main__":
	unittest.main()
