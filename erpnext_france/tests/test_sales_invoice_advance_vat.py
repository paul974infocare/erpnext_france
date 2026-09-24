import inspect
import unittest
from unittest.mock import Mock, patch

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from erpnext_france import hooks
from erpnext_france.erpnext_france.overrides.sales_invoice_advance_vat import (
	make_regional_gl_entries,
)
from erpnext_france.erpnext_france.overrides.doctype.sales_invoice_france import SalesInvoiceFrance

HOOK_PATH = "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_regional_gl_entries"
IMPLEMENTATION_PATH = (
	"erpnext_france.erpnext_france.overrides.sales_invoice_advance_vat.make_regional_gl_entries"
)


class TestSalesInvoiceAdvanceVAT(unittest.TestCase):
	def make_sales_invoice(self, advances=None, sales_orders=("SO-1",), name="SI-1"):
		doc = frappe._dict(
			{
				"doctype": "Sales Invoice",
				"name": name,
				"company": "Company 1",
				"customer": "Customer 1",
				"cost_center": "Main - C1",
				"advances": advances or [],
				"items": [frappe._dict({"sales_order": sales_order}) for sales_order in sales_orders],
			}
		)
		doc.get_gl_dict = Mock(side_effect=lambda args, item=None: frappe._dict(args))
		return doc

	def make_advance(self, reference_name, allocated_amount):
		return frappe._dict(
			{
				"reference_type": "Payment Entry",
				"reference_name": reference_name,
				"allocated_amount": allocated_amount,
			}
		)

	def make_dpi(self, name="DPI-1", grand_total=325.5, taxes=None, sales_order="SO-1"):
		return frappe._dict(
			{
				"name": name,
				"docstatus": 1,
				"company": "Company 1",
				"customer": "Customer 1",
				"sales_order": sales_order,
				"currency": "EUR",
				"grand_total": grand_total,
				"taxes": taxes or [frappe._dict({"tax_amount": 25.5, "tax_account": "445785"})],
				"precision": lambda fieldname: 2,
			}
		)

	def make_pe(self, name="PE-1", dpi="DPI-1"):
		return frappe._dict(
			{
				"name": name,
				"docstatus": 1,
				"payment_type": "Receive",
				"party_type": "Customer",
				"party": "Customer 1",
				"company": "Company 1",
				"down_payment_invoice": dpi,
			}
		)

	def invoke(
		self,
		doc,
		payment_entries,
		dpis,
		recognized_tax=None,
		gl_entries=None,
		active_sales_invoices=None,
		sales_invoice_advances=None,
		previous_reversals=None,
	):
		recognized_tax = recognized_tax or {}
		gl_entries = gl_entries if gl_entries is not None else []
		active_sales_invoices = active_sales_invoices or []
		sales_invoice_advances = sales_invoice_advances or []
		previous_reversals = previous_reversals or []

		def get_doc(doctype, name):
			return payment_entries[name] if doctype == "Payment Entry" else dpis[name]

		def get_value(doctype, name, fieldname, **kwargs):
			if doctype == "Sales Order":
				return "EUR"
			if fieldname == "default_currency":
				return "EUR"
			return "44588"

		def get_all(doctype, **kwargs):
			if doctype == "Payment Entry":
				dpi_name = kwargs["filters"]["down_payment_invoice"]
				return [
					name
					for name, payment_entry in payment_entries.items()
					if payment_entry.down_payment_invoice == dpi_name
				]
			if doctype == "Sales Invoice":
				return [
					name
					for name in active_sales_invoices
					if name != kwargs["filters"]["name"][1]
				]
			if doctype == "Sales Invoice Advance":
				return [
					frappe._dict({"allocated_amount": advance["allocated_amount"]})
					for advance in sales_invoice_advances
					if advance["parent"] in kwargs["filters"]["parent"][1]
					and advance["reference_name"] in kwargs["filters"]["reference_name"][1]
				]
			if doctype != "GL Entry":
				return []
			filters = kwargs["filters"]
			if filters["voucher_type"] == "Sales Invoice":
				return [
					frappe._dict({"account": account, "debit": amount})
					for account, amount in previous_reversals
				]
			dpi_name = filters["france_advance_vat_reference"]
			return [
				frappe._dict({"account": account, "credit": amount})
				for account, amount in recognized_tax.get(dpi_name, {}).items()
			]

		with (
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(frappe, "get_system_settings", return_value="Banker's Rounding (legacy)"),
		):
			return make_regional_gl_entries(gl_entries, doc)

	def test_override_is_declared_for_france_and_reunion(self):
		self.assertEqual(hooks.regional_overrides["France"][HOOK_PATH], IMPLEMENTATION_PATH)
		self.assertEqual(hooks.regional_overrides["Réunion"][HOOK_PATH], IMPLEMENTATION_PATH)

	def test_override_matches_erpnext_contract(self):
		self.assertEqual(tuple(inspect.signature(make_regional_gl_entries).parameters), ("gl_entries", "doc"))

	def test_sales_invoice_france_uses_v16_regional_gl_builder(self):
		self.assertIs(SalesInvoiceFrance.get_gl_entries, SalesInvoice.get_gl_entries)
		doc = Mock(spec=SalesInvoiceFrance)
		for method_name in (
				"make_customer_gl_entry",
				"make_tax_gl_entries",
				"make_internal_transfer_gl_entries",
				"make_item_gl_entries",
				"make_precision_loss_gl_entry",
				"make_discount_gl_entries",
				"make_loyalty_point_redemption_gle",
				"make_pos_gl_entries",
				"make_write_off_gl_entry",
				"make_gle_for_rounding_adjustment",
				"set_transaction_currency_and_rate_in_gl_map",
		):
			getattr(doc, method_name).return_value = None

		with (
			patch("erpnext.accounts.general_ledger.merge_similar_entries", side_effect=lambda entries: entries),
			patch(
				"erpnext.accounts.doctype.sales_invoice.sales_invoice.make_regional_gl_entries",
				side_effect=lambda entries, regional_doc: entries + [{"regional": regional_doc}],
			) as regional_hook,
		):
			result = SalesInvoiceFrance.get_gl_entries(doc)

		regional_hook.assert_called_once_with([], doc)
		self.assertEqual(result, [{"regional": doc}])

	def test_noop_without_payment_entry_advance(self):
		gl_entries = [{"account": "4111", "debit": 100}]
		result = make_regional_gl_entries(gl_entries, self.make_sales_invoice())
		self.assertIs(result, gl_entries)
		self.assertEqual(len(gl_entries), 1)

	def test_simple_advance_vat_recovery(self):
		doc = self.make_sales_invoice([self.make_advance("PE-1", 100)])
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
		)
		self.assertEqual([(entry.account, entry.debit, entry.credit) for entry in gl_entries], [("445785", 7.83, 0), ("44588", 0, 7.83)])

	def test_partial_advance_uses_allocated_amount(self):
		doc = self.make_sales_invoice([self.make_advance("PE-1", 50)])
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
		)
		self.assertEqual(gl_entries[0].debit, 3.92)
		self.assertEqual(gl_entries[1].credit, 3.92)

	def test_multiple_payment_entries_for_one_dpi_are_combined(self):
		doc = self.make_sales_invoice(
			[self.make_advance("PE-1", 100), self.make_advance("PE-2", 100)]
		)
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe("PE-1"), "PE-2": self.make_pe("PE-2")},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
		)
		self.assertEqual(gl_entries[0].debit, 15.67)

	def test_multiple_tax_accounts_and_rates_are_preserved(self):
		taxes = [
			frappe._dict({"tax_amount": 100, "tax_account": "445710"}),
			frappe._dict({"tax_amount": 50, "tax_account": "445720"}),
		]
		doc = self.make_sales_invoice([self.make_advance("PE-1", 500)])
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi(grand_total=1000, taxes=taxes)},
			recognized_tax={"DPI-1": {"445710": 100, "445720": 50}},
		)
		self.assertEqual(
			[(entry.account, entry.debit, entry.credit) for entry in gl_entries],
			[("445710", 50, 0), ("44588", 0, 50), ("445720", 25, 0), ("44588", 0, 25)],
		)

	def test_same_tax_account_is_aggregated(self):
		taxes = [
			frappe._dict({"tax_amount": 100, "tax_account": "445785"}),
			frappe._dict({"tax_amount": 50, "tax_account": "445785"}),
		]
		doc = self.make_sales_invoice([self.make_advance("PE-1", 500)])
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi(grand_total=1000, taxes=taxes)},
			recognized_tax={"DPI-1": {"445785": 150}},
		)
		self.assertEqual(len(gl_entries), 2)
		self.assertEqual(gl_entries[0].debit, 75)

	def test_recovery_is_capped_by_recognized_payment_entry_tax(self):
		doc = self.make_sales_invoice([self.make_advance("PE-1", 325.5)])
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 7.83}},
		)
		self.assertEqual(gl_entries[0].debit, 7.83)
		self.assertEqual(gl_entries[1].credit, 7.83)

	def test_multiple_dpis_are_recovered_separately(self):
		doc = self.make_sales_invoice(
			[self.make_advance("PE-1", 100), self.make_advance("PE-2", 100)],
			sales_orders=("SO-1", "SO-2"),
		)
		gl_entries = self.invoke(
			doc,
			{"PE-1": self.make_pe("PE-1", "DPI-1"), "PE-2": self.make_pe("PE-2", "DPI-2")},
			{"DPI-1": self.make_dpi("DPI-1"), "DPI-2": self.make_dpi("DPI-2", sales_order="SO-2")},
			recognized_tax={"DPI-1": {"445785": 25.5}, "DPI-2": {"445785": 25.5}},
		)
		self.assertEqual(len(gl_entries), 4)
		self.assertEqual({entry.france_advance_vat_reference for entry in gl_entries}, {"DPI-1", "DPI-2"})

	def test_both_lines_have_provenance_and_native_lines_are_unchanged(self):
		native_entry = {"account": "4111", "debit": 100}
		gl_entries = self.invoke(
			self.make_sales_invoice([self.make_advance("PE-1", 100)]),
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
			gl_entries=[native_entry],
		)
		self.assertIs(gl_entries[0], native_entry)
		self.assertTrue(all(entry._skip_merge for entry in gl_entries[1:]))
		self.assertEqual(
			[entry.france_advance_vat_reference for entry in gl_entries[1:]],
			["DPI-1", "DPI-1"],
		)

	def test_recovery_is_cumulative_across_sales_invoices(self):
		gl_entries = self.invoke(
			self.make_sales_invoice(
				[self.make_advance("PE-1", 100)], name="SI-2"
			),
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
			active_sales_invoices=["SI-1"],
			sales_invoice_advances=[
				{"parent": "SI-1", "reference_name": "PE-1", "allocated_amount": 100}
			],
			previous_reversals=[("445785", 7.83)],
		)
		self.assertEqual(gl_entries[0].debit, 7.84)
		self.assertEqual(gl_entries[1].credit, 7.84)

	def test_cancelled_sales_invoice_is_excluded_from_history(self):
		gl_entries = self.invoke(
			self.make_sales_invoice([self.make_advance("PE-1", 100)], name="SI-2"),
			{"PE-1": self.make_pe()},
			{"DPI-1": self.make_dpi()},
			recognized_tax={"DPI-1": {"445785": 25.5}},
			active_sales_invoices=[],
			sales_invoice_advances=[
				{"parent": "SI-CANCELLED", "reference_name": "PE-1", "allocated_amount": 100}
			],
			previous_reversals=[("445785", 7.83)],
		)
		self.assertEqual(gl_entries[0].debit, 7.83)


	def test_currency_mismatch_is_rejected(self):
		dpi = self.make_dpi()
		dpi.currency = "USD"
		with self.assertRaises(Exception):
			self.invoke(
				self.make_sales_invoice([self.make_advance("PE-1", 100)]),
				{"PE-1": self.make_pe()},
				{"DPI-1": dpi},
				recognized_tax={"DPI-1": {"445785": 25.5}},
			)
