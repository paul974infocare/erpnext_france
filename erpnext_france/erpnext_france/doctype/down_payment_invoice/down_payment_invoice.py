import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class DownPaymentInvoice(Document):
    @property
    def paid_amount(self):
        if hasattr(self, "_paid_amount_cache"):
            return self._paid_amount_cache

        precision = self.precision("grand_total")
        payment_entries = frappe.get_all(
            "Payment Entry",
            filters={
                "down_payment_invoice": self.name,
                "docstatus": 1,
                "payment_type": "Receive",
                "company": self.company,
                "party_type": "Customer",
                "party": self.customer,
            },
            fields=["down_payment_invoice_amount"],
        )
        self._paid_amount_cache = flt(
            sum(flt(payment_entry.get("down_payment_invoice_amount")) for payment_entry in payment_entries),
            precision,
        )
        return self._paid_amount_cache

    @property
    def outstanding_amount(self):
        precision = self.precision("grand_total")
        return flt(max(flt(self.grand_total) - self.paid_amount, 0), precision)

    @property
    def payment_status(self):
        if self.paid_amount <= 0:
            return "Unpaid"
        if self.outstanding_amount <= 0:
            return "Paid"
        return "Partly Paid"

    def validate(self):
        self.validate_sales_order()
        self.validate_calculation_method()
        self.calculate_totals()

    def validate_sales_order(self):
        if not self.sales_order:
            frappe.throw(_("Sales Order is mandatory"))

        sales_order = frappe.get_cached_doc("Sales Order", self.sales_order)
        if sales_order.docstatus != 1:
            frappe.throw(_("Sales Order {0} must be submitted").format(self.sales_order))

        if self.is_new():
            self.company = sales_order.company
            self.customer = sales_order.customer
            self.customer_name = sales_order.customer_name
            self.currency = sales_order.currency
            self.conversion_rate = flt(sales_order.conversion_rate or 1)
        else:
            for fieldname in ("company", "customer", "customer_name", "currency"):
                if self.get(fieldname) != sales_order.get(fieldname):
                    frappe.throw(
                        _("{0} must match Sales Order {1}").format(
                            self.meta.get_label(fieldname), self.sales_order
                        )
                    )

            if flt(self.conversion_rate) != flt(sales_order.conversion_rate or 1):
                frappe.throw(
                    _("{0} must match Sales Order {1}").format(
                        self.meta.get_label("conversion_rate"), self.sales_order
                    )
                )

        self.posting_date = getdate(self.posting_date or today())

    def validate_calculation_method(self):
        if self.calculation_method not in ("ByPercent", "ByAmount"):
            frappe.throw(_("Calculation Method must be ByPercent or ByAmount"))

        if self.calculation_method == "ByPercent":
            if not 0 <= flt(self.advance_percentage) <= 100:
                frappe.throw(_("Advance Percentage must be between 0 and 100"))
        elif not 0 <= flt(self.advance_amount) <= flt(self.get_sales_order().grand_total):
            frappe.throw(_("Advance Amount must be between 0 and the Sales Order total"))

    def calculate_totals(self):
        sales_order = self.get_sales_order()
        factor = (
            flt(self.advance_percentage) / 100
            if self.calculation_method == "ByPercent"
            else flt(self.advance_amount) / flt(sales_order.grand_total)
            if sales_order.grand_total
            else 0
        )

        self.set("taxes", [])
        net_total = 0
        total_taxes = 0
        tax_breakdown = self.get_tax_breakdown(sales_order)
        for (tax_rate, tax_account), values in tax_breakdown.items():
            taxable_amount = flt(values["taxable_amount"] * factor, self.precision("net_total"))
            tax_amount = flt(values["tax_amount"] * factor, self.precision("total_taxes_and_charges"))
            net_total += taxable_amount
            total_taxes += tax_amount
            self.append(
                "taxes",
                {
                    "tax_rate": tax_rate,
                    "taxable_amount": taxable_amount,
                    "tax_amount": tax_amount,
                    "tax_account": tax_account,
                },
            )

        self.net_total = net_total
        self.total_taxes_and_charges = total_taxes
        self.grand_total = flt(net_total + total_taxes, self.precision("grand_total"))
        self.base_net_total = flt(self.net_total * self.conversion_rate)
        self.base_total_taxes_and_charges = flt(self.total_taxes_and_charges * self.conversion_rate)
        self.base_grand_total = flt(self.grand_total * self.conversion_rate)

    def get_sales_order(self):
        return frappe.get_cached_doc("Sales Order", self.sales_order)

    @staticmethod
    def get_tax_breakdown(sales_order):
        breakdown = {}
        tax_accounts = {tax_row.name: tax_row.account_head for tax_row in sales_order.get("taxes") or []}
        for detail in sales_order.get("item_wise_tax_details") or []:
            tax_rate = flt(detail.rate)
            tax_account = tax_accounts.get(detail.tax_row)
            values = breakdown.setdefault((tax_rate, tax_account), {"taxable_amount": 0, "tax_amount": 0})
            values["taxable_amount"] += flt(detail.taxable_amount)
            values["tax_amount"] += flt(detail.amount)

        if breakdown:
            return breakdown

        if sales_order.total_taxes_and_charges:
            tax_rate = (
                flt(sales_order.total_taxes_and_charges / sales_order.net_total * 100)
                if sales_order.net_total
                else 0
            )
            return {
                (tax_rate, None): {
                    "taxable_amount": flt(sales_order.net_total),
                    "tax_amount": flt(sales_order.total_taxes_and_charges),
                }
            }

        return {(0, None): {"taxable_amount": flt(sales_order.net_total), "tax_amount": 0}}


@frappe.whitelist()
def make_down_payment_invoice(sales_order, calculation_method, value):
    doc = frappe.new_doc("Down Payment Invoice")
    doc.update(
        {
            "sales_order": sales_order,
            "calculation_method": calculation_method,
            "advance_percentage": value if calculation_method == "ByPercent" else 0,
            "advance_amount": value if calculation_method == "ByAmount" else 0,
        }
    )
    doc.insert()
    return doc
