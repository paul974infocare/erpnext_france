import frappe

from erpnext_france.erpnext_france.overrides.doctype.chart_of_accounts import SUPPORTED_COUNTRIES


ACCOUNT_NUMBERS = ("4452", "4453")
LIABILITY_BRANCH_ACCOUNT_NAME = "4457-Taxes sur le chiffre d'affaires collectées"


def execute():
	companies = frappe.get_all(
		"Company",
		filters={"country": ["in", SUPPORTED_COUNTRIES]},
		fields=["name"],
	)

	for company in companies:
		_move_accounts_for_company(company.name)


def _move_accounts_for_company(company):
	target_parent = _get_liability_445_parent(company)
	if not target_parent:
		frappe.log_error(
			message=(
				f"Unable to locate the Liability 445 parent for Company {company}. "
				f"Accounts {', '.join(ACCOUNT_NUMBERS)} were not modified."
			),
			title="ERPNext France: missing Liability 445 account",
		)
		return

	for account_number in ACCOUNT_NUMBERS:
		_move_account(company, account_number, target_parent)


def _get_liability_445_parent(company):
	return frappe.db.get_value(
		"Account",
		{
			"account_name": LIABILITY_BRANCH_ACCOUNT_NAME,
			"company": company,
			"root_type": "Liability",
			"is_group": 1,
		},
		"parent_account",
	)


def _move_account(company, account_number, target_parent):
	account_name = frappe.db.get_value(
		"Account",
		{"company": company, "account_number": account_number},
		"name",
	)

	if not account_name:
		return

	account = frappe.get_doc("Account", account_name)

	if (
		account.parent_account == target_parent
		and account.root_type == "Liability"
		and account.account_type == "Tax"
		and not account.is_group
	):
		return

	if account.account_type != "Tax" or account.is_group:
		frappe.log_error(
			message=(
				f"Account {account_number} for Company {company} is incompatible "
				f"with the expected Tax leaf account and was not modified: "
				f"{account.as_dict()}"
			),
			title=f"ERPNext France: incompatible account {account_number}",
		)
		return

	account.parent_account = target_parent
	account.save(ignore_permissions=True)
