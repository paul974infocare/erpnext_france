import frappe

from erpnext_france.erpnext_france.overrides.doctype.chart_of_accounts import SUPPORTED_COUNTRIES

ACCOUNT_NUMBER = "44588"
PARENT_ACCOUNT_NAME = "4458-Taxes sur le chiffre d'affaires à régulariser ou en attente"
ACCOUNT_NAME = "TVA sur acomptes à régulariser"


def execute():
	companies = frappe.get_all(
		"Company",
		filters={"country": ["in", SUPPORTED_COUNTRIES]},
		fields=["name"],
	)

	for company in companies:
		_create_account_for_company(company.name)


def _create_account_for_company(company):
	parent_account = frappe.db.get_value(
		"Account",
		{
			"account_name": PARENT_ACCOUNT_NAME,
			"company": company,
			"root_type": "Asset",
			"is_group": 1,
		},
		"name",
	)
	if not parent_account:
		return

	existing_account = frappe.db.get_value(
		"Account",
		{"account_number": ACCOUNT_NUMBER, "company": company},
		[
			"name",
			"parent_account",
			"root_type",
			"account_type",
			"is_group",
		],
		as_dict=True,
	)
	if existing_account:
		if _is_compatible_account(existing_account, parent_account):
			return

		frappe.log_error(
			message=(
				f"Account {ACCOUNT_NUMBER} for Company {company} is incompatible with the expected "
				f"Asset/Tax account under parent {parent_account}: {existing_account}"
			),
			title="ERPNext France: incompatible account 44588",
		)
		return

	account = frappe.new_doc("Account")
	account.update(
		{
			"account_name": ACCOUNT_NAME,
			"account_number": ACCOUNT_NUMBER,
			"account_type": "Tax",
			"company": company,
			"parent_account": parent_account,
		}
	)
	account.insert(ignore_permissions=True)


def _is_compatible_account(account, parent_account):
	return (
		account.parent_account == parent_account
		and account.root_type == "Asset"
		and account.account_type == "Tax"
		and not account.is_group
	)
