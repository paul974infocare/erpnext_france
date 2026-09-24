// Copyright (c) 2021, Scopen and contributors
// For license information, please see license.txt
frappe.ui.form.on("Sales Order", "refresh", async function (frm) {
  frm.set_query("payment_terms_template", function () {
    return {
      filters: {
        template_payment_terms_before_invoice: 1,
      },
    };
  });
  frm.set_query("payment_term", "payment_schedule", function (frm, cdt, cdn) {
    return {
      filters: {
        payment_terms_before_invoice: 1,
      },
    };
  });
  await prevent_term_modification_if_payment_exist(frm);
});

frappe.ui.form.on("Sales Order", {
  payment_terms_template: function (frm) {
    if (!frm.doc.payment_terms_template) {
      frm.set_value("payment_schedule", []);
      return;
    }
    frappe.call({
      method:
        "erpnext_france.controllers.party.get_payment_terms_before_invoice",
      args: {
        doctype: frm.doc.doctype,
        grand_total: frm.doc.grand_total,
        base_grand_total: frm.doc.base_grand_total,
        posting_date: frm.doc.transaction_date,
        delivery_date: frm.doc.delivery_date,
        payment_terms_template: frm.doc.payment_terms_template,
      },
      callback: function (r) {
        if (r.message) {
          frm.set_value("payment_schedule", r.message);
        }
      },
    });
  },
});

async function prevent_term_modification_if_payment_exist(frm) {
  const response = await frappe.call({
    method: "erpnext_france.controllers.payment_entry_ref.payment_entry_ref",
    freeze: true,
    args: {
      reference_doctype: "Sales Order",
      reference_name: frm.doc.name,
    },
  });

  let payments = response.message;
  let payments_array = payments.map((payment) => payment.payment_term);
  for (let idx in frm.doc.payment_schedule) {
    if (!payments_array.includes(frm.doc.payment_schedule[idx].payment_term)) {
      continue;
    }
    frm.set_df_property("payment_schedule", "read_only", 1);
    let grid_row = frm.fields_dict.payment_schedule.grid.grid_rows[idx];
    for (let field of grid_row.docfields) {
      frm.set_df_property(
        "payment_schedule",
        "read_only",
        1,
        frm.doc.name,
        field.fieldname,
        grid_row.doc.name
      );
    }
  }
}
