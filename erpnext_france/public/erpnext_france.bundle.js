erpnext.TransactionController.prototype.payment_terms_template =
  async function (doc, doctype, docname) {
    if (erpnext.TransactionController) {
      // Instanciation de la classe et assignation à une propriété du formulaire
      this.frm.transaction_controller = new erpnext.TransactionController({
        frm: this.frm,
      });
    }

    let me = this;

    if (
      ["Quotation", "Sales Order"].includes(doctype) &&
      doc.payment_terms_template
    ) {
      get_payment_terms_before_invoice(
        me,
        doctype,
        doc.rounded_total || doc.grand_total,
        doc.base_rounded_total || doc.base_grand_total,
        doc.posting_date || doc.transaction_date,
        doc.delivery_date,
        doc.payment_terms_template
      );
    } else if (doctype == "Sales Invoice") {
      let posting_date = null;
      if (doc.items.length > 0 && doc.items[0].sales_order) {
        let sales_order = doc.items[0].sales_order;
        frappe.call({
          method: "frappe.client.get_value",
          args: {
            doctype: "Sales Order",
            name: sales_order,
            fieldname: "transaction_date",
          },
          callback: function (r) {
            let transaction_date = r.message.transaction_date;
            if (transaction_date) {
              get_payment_terms_before_invoice(
                me,
                doctype,
                doc.rounded_total || doc.grand_total,
                doc.base_rounded_total || doc.base_grand_total,
                transaction_date,
                doc.posting_date,
                doc.payment_terms_template
              );
            }
          },
        });
      }
    }
  };

function get_payment_terms_before_invoice(
  me,
  doctype,
  grand_total,
  base_grand_total,
  posting_date,
  delivery_date,
  payment_terms_template
) {
  frappe.call({
    method: "erpnext_france.controllers.party.get_payment_terms_before_invoice",
    args: {
      doctype: doctype,
      grand_total: grand_total,
      base_grand_total: base_grand_total,
      posting_date: posting_date,
      delivery_date: delivery_date,
      payment_terms_template: payment_terms_template,
    },
    callback: function (r) {
      if (r.message && !r.exc) {
        me.frm.set_value("payment_schedule", r.message);
        const company_currency =
          me.frm.transaction_controller.get_company_currency();
        me.frm.transaction_controller.update_payment_schedule_grid_labels(
          company_currency
        );
      }
    },
  });
}

frappe.update_doc_with_sirene_info = async function (doc, entity, doctype) {
  const baseFields = {};
  const addressFields = {};

  if (doctype === "Customer") {
    baseFields["customer_name"] = entity.company_name;
    baseFields["customer_type"] = entity.entity_type;
  } else {
    baseFields["supplier_name"] = entity.company_name;
    baseFields["supplier_type"] = entity.entity_type;
  }

  baseFields["siret"] = entity.siret;
  baseFields["siren"] = entity.siren;
  baseFields["code_naf"] = await frappe.getCodeNaf(entity.code_naf);
  baseFields["legal_form"] = await frappe.getLegalForm(entity.legal_form);
  baseFields["tax_id"] = entity.tax_id;

  addressFields["address_line1"] = entity.address_1;
  addressFields["city"] = entity.town;
  addressFields["pincode"] = entity.zipcode;
  addressFields["country"] = entity.country;

  let response = await frappe.updateDoctype(doctype, doc.name, baseFields);

  const addressName =
    doctype === "Customer"
      ? doc.customer_primary_address
      : doc.supplier_primary_address;

  if (addressName) {
    await frappe.updateDoctype("Address", addressName, addressFields);
  }
  return response;
};

frappe.updateDoctype = async function (doctype, docname, fields) {
  if (Object.keys(fields).length === 0) return;

  return new Promise((resolve, reject) => {
    frappe.call({
      method: "frappe.client.set_value",
      args: {
        doctype: doctype,
        name: docname,
        fieldname: fields,
      },

      callback: function (r) {
        if (r.exc) reject(r.exc);
        else resolve(r.message);
      },
      error: reject,
    });
  });
};

frappe.getCodeNaf = async function (code_naf) {
  let naf = await frappe.db.get_doc("Code Naf", null, { code: code_naf });
  return naf.name;
};

frappe.getLegalForm = async function getLegalForm(legal_form) {
  let form = await frappe.db.get_doc("Legal Form", null, { code: legal_form });
  return form.name;
};
frappe.getLegalFormByName = async function getLegalForm(legal_form) {
  let form = await frappe.db.get_doc("Legal Form", null, { label: legal_form });
  return form.name;
};
