import inspect
import unittest
from unittest.mock import Mock, patch

import frappe

from erpnext_france import hooks
from erpnext_france.erpnext_france.overrides import payment_entry as payment_entry_override
from erpnext_france.erpnext_france.overrides.payment_entry import add_regional_gl_entries

HOOK_PATH = "erpnext.accounts.doctype.payment_entry.payment_entry.add_regional_gl_entries"
IMPLEMENTATION_PATH = "erpnext_france.erpnext_france.overrides.payment_entry.add_regional_gl_entries"


class TestPaymentEntryRegionalOverride(unittest.TestCase):
	def make_payment_entry(
		self, allocated_amount=0, name="PE-CURRENT", references=True, down_payment_invoice="DPI-1"
	):
		payment_entry = frappe._dict(
			{
				"name": name,
				"payment_type": "Receive",
				"party_type": "Customer",
				"party": "Customer 1",
				"company": "Company 1",
				"down_payment_invoice": down_payment_invoice,
				"transaction_exchange_rate": 1,
				"cost_center": "Main - C1",
				"references": (
					[
						frappe._dict(
							{
								"reference_doctype": "Sales Order",
								"reference_name": "SO-1",
								"allocated_amount": allocated_amount,
							}
						)
					]
					if references
					else []
				),
			}
		)
		payment_entry.get_gl_dict = Mock(side_effect=lambda args, item=None: frappe._dict(args))
		return payment_entry

	def make_down_payment_invoice(self, taxes, grand_total=325.5):
		return frappe._dict(
			{
				"name": "DPI-1",
				"docstatus": 1,
				"company": "Company 1",
				"customer": "Customer 1",
				"sales_order": "SO-1",
				"currency": "EUR",
				"grand_total": grand_total,
				"taxes": taxes,
				"precision": lambda fieldname: 2,
			}
		)

	def test_down_payment_invoice_currency_must_match_company_currency(self):
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)

		with self.assertRaises(Exception):
			self.invoke(
				payment_entry,
				down_payment_invoice,
				sales_order_currency="USD",
			)

	def invoke(
		self,
		payment_entry,
		down_payment_invoice,
		previous_entries=None,
		gl_entries=None,
		account="44588",
		sales_order_currency="EUR",
	):
		previous_entries = previous_entries or []
		gl_entries = gl_entries if gl_entries is not None else []

		with (
			patch.object(frappe, "get_doc", return_value=down_payment_invoice),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=lambda doctype, *args, **kwargs: (
					frappe._dict(
						{
							"currency": sales_order_currency,
						}
					)
					if doctype == "Sales Order"
					else "EUR"
					if doctype == "Company" and args[1] == "default_currency"
					else account
				),
			),
			patch.object(frappe, "get_system_settings", return_value="Banker's Rounding (legacy)"),
			patch.object(
				payment_entry_override,
				"_get_previous_allocations",
				return_value=100 if previous_entries else 0,
			),
			patch.object(
				payment_entry_override,
				"_get_previous_tax_entries",
				return_value={entry["account"]: entry["credit"] for entry in gl_entries if previous_entries},
			),
		):
			add_regional_gl_entries(gl_entries, payment_entry)
		return gl_entries

	def test_override_is_declared_for_france_and_reunion(self):
		self.assertEqual(hooks.regional_overrides["France"][HOOK_PATH], IMPLEMENTATION_PATH)
		self.assertEqual(hooks.regional_overrides["Réunion"][HOOK_PATH], IMPLEMENTATION_PATH)

	def test_override_matches_erpnext_contract(self):
		self.assertEqual(tuple(inspect.signature(add_regional_gl_entries).parameters), ("gl_entries", "doc"))

	def test_override_is_a_noop(self):
		gl_entries = [{"account": "111000 - Banque - FC", "debit": 100}]
		original_entries = [entry.copy() for entry in gl_entries]

		result = add_regional_gl_entries(gl_entries, frappe._dict())

		self.assertIsNone(result)
		self.assertEqual(gl_entries, original_entries)

	def test_payment_entry_without_down_payment_invoice_is_a_noop(self):
		gl_entries = [{"account": "111000 - Banque - FC", "debit": 100}]

		add_regional_gl_entries(gl_entries, self.make_payment_entry(down_payment_invoice=""))

		self.assertEqual(len(gl_entries), 1)

	def test_down_payment_invoice_without_tax_is_a_noop(self):
		gl_entries = [{"account": "111000 - Banque - FC", "debit": 100}]
		payment_entry = self.make_payment_entry(100)

		with patch.object(frappe, "get_doc", return_value=self.make_down_payment_invoice([])):
			add_regional_gl_entries(gl_entries, payment_entry)

		self.assertEqual(len(gl_entries), 1)

	def test_missing_advance_vat_account_raises(self):
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)

		with self.assertRaises(Exception), patch.object(frappe.db, "get_value", return_value=None):
			self.invoke(payment_entry, down_payment_invoice, account=None)

	def test_missing_tax_account_raises(self):
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice([frappe._dict({"tax_amount": 25.5})])

		with self.assertRaises(Exception):
			self.invoke(payment_entry, down_payment_invoice)

	def test_partial_payment_posts_cumulative_tax(self):
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)
		gl_entries = self.invoke(
			payment_entry,
			down_payment_invoice,
			gl_entries=[{"account": "111000 - Banque - FC", "debit": 100}],
		)

		self.assertEqual(len(gl_entries), 3)
		self.assertEqual(gl_entries[1].debit, 7.83)
		self.assertEqual(gl_entries[2].credit, 7.83)

	def test_second_payment_absorbs_rounding_difference(self):
		payment_entry = self.make_payment_entry(225.5)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)

		self.invoke(
			payment_entry,
			down_payment_invoice,
			previous_entries=["PE-1"],
			gl_entries=[{"account": "445785", "credit": 7.83}],
		)

		debit_entry = payment_entry.get_gl_dict.call_args_list[0].args[0]
		self.assertEqual(debit_entry["account"], "44588")
		self.assertEqual(debit_entry["debit"], 17.67)
		self.assertEqual(debit_entry["france_advance_vat_reference"], "DPI-1")
		self.assertTrue(debit_entry["_skip_merge"])

	def test_multiple_tax_accounts_are_posted_separately(self):
		payment_entry = self.make_payment_entry(500)
		down_payment_invoice = self.make_down_payment_invoice(
			[
				frappe._dict({"tax_amount": 100, "tax_account": "445710"}),
				frappe._dict({"tax_amount": 50, "tax_account": "445720"}),
			],
			grand_total=1000,
		)
		gl_entries = self.invoke(
			payment_entry,
			down_payment_invoice,
			gl_entries=[{"account": "111000 - Banque - FC", "debit": 500}],
		)

		self.assertEqual(len(gl_entries), 5)
		self.assertEqual(
			[(entry.account, entry.debit, entry.credit) for entry in gl_entries[1:]],
			[("44588", 50, 0), ("445710", 0, 50), ("44588", 25, 0), ("445720", 0, 25)],
		)

	def test_multiple_tax_rates_same_account_are_aggregated_without_overwrite(self):
		payment_entry = self.make_payment_entry(500)
		down_payment_invoice = self.make_down_payment_invoice(
			[
				frappe._dict({"tax_amount": 100, "tax_account": "445785", "tax_rate": 5.5}),
				frappe._dict({"tax_amount": 50, "tax_account": "445785", "tax_rate": 20}),
			],
			grand_total=1000,
		)
		gl_entries = self.invoke(payment_entry, down_payment_invoice)

		self.assertEqual(len(gl_entries), 2)
		self.assertEqual(gl_entries[0].debit, 75)
		self.assertEqual(gl_entries[1].credit, 75)
		self.assertEqual(gl_entries[0].account, "44588")
		self.assertEqual(gl_entries[1].account, "445785")

	def test_current_payment_rebuilds_tax_from_submitted_previous_payment(self):
		payment_entry = self.make_payment_entry(100, name="PE-CURRENT")
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)
		gl_entries = self.invoke(
			payment_entry,
			down_payment_invoice,
			previous_entries=["PE-SUBMITTED"],
			gl_entries=[{"account": "445785", "credit": 7.83}],
		)

		self.assertEqual(gl_entries[1].debit, 7.84)
		self.assertEqual(gl_entries[2].credit, 7.84)

	def test_previous_allocations_use_names_returned_by_pluck_for_second_payment(self):
		doc = self.make_payment_entry(name="PE-CURRENT")
		down_payment_invoice = self.make_down_payment_invoice([])
		calls = []

		def get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			if doctype == "Payment Entry":
				return ["PE-1", "PE-2"]
			return [
				frappe._dict({"allocated_amount": 100}),
				frappe._dict({"allocated_amount": 25.5}),
			]

		with patch.object(frappe, "get_all", side_effect=get_all):
			result = payment_entry_override._get_previous_allocations(
				doc, down_payment_invoice, precision=2
			)

		self.assertEqual(result, 125.5)
		self.assertEqual(calls[0][1]["pluck"], "name")
		self.assertEqual(
			calls[1][1]["filters"]["parent"],
			["in", ["PE-1", "PE-2"]],
		)

	def test_native_gl_entries_are_only_appended_to(self):
		native_entry = {"account": "111000 - Banque - FC", "debit": 100}
		gl_entries = [native_entry]
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)

		gl_entries = self.invoke(
			payment_entry,
			down_payment_invoice,
			gl_entries=gl_entries,
		)

		self.assertIs(gl_entries[0], native_entry)
		self.assertEqual(len(gl_entries), 3)

	def test_both_regional_entries_carry_dpi_provenance(self):
		payment_entry = self.make_payment_entry(100)
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)

		self.invoke(payment_entry, down_payment_invoice)

		calls = [call.args[0] for call in payment_entry.get_gl_dict.call_args_list]
		self.assertEqual(
			[c["france_advance_vat_reference"] for c in calls],
			["DPI-1", "DPI-1"],
		)
		self.assertTrue(all(c["_skip_merge"] for c in calls))

	def test_previous_gl_query_requires_dpi_provenance(self):
		doc = self.make_payment_entry()
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)
		with patch.object(
			frappe,
			"get_all",
			side_effect=[
				["PE-1", "PE-OTHER"],
				[{"account": "445785", "credit": 7.83}],
			],
		) as get_all:
			result = payment_entry_override._get_previous_tax_entries(
				doc, down_payment_invoice, {"445785": 25.5}
			)

		self.assertEqual(result, {"445785": 7.83})
		filters = get_all.call_args_list[1].kwargs["filters"]
		self.assertEqual(filters["france_advance_vat_reference"], "DPI-1")
		self.assertEqual(filters["is_cancelled"], 0)
		self.assertEqual(filters["voucher_no"], ["in", ["PE-1", "PE-OTHER"]])
		self.assertEqual(filters["account"], ["in", ["445785"]])
		self.assertEqual(
			get_all.call_args_list[0].kwargs["filters"]["name"],
			["!=", "PE-CURRENT"],
		)

	def test_native_same_tax_account_is_not_selected_without_provenance(self):
		doc = self.make_payment_entry()
		down_payment_invoice = self.make_down_payment_invoice(
			[frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})]
		)
		with patch.object(
			frappe,
			"get_all",
			side_effect=[
				["PE-1"],
				[{"account": "445785", "credit": 7.83}],
			],
		) as get_all:
			payment_entry_override._get_previous_tax_entries(doc, down_payment_invoice, {"445785": 25.5})

		self.assertEqual(
			get_all.call_args_list[1].kwargs["filters"]["france_advance_vat_reference"],
			"DPI-1",
		)

