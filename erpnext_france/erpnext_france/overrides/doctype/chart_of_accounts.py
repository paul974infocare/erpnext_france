import json
import os

import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
    get_account_tree_from_existing_company,
    get_chart as erpnext_get_chart,
    get_charts_for_country as erpnext_get_charts_for_country,
)


SUPPORTED_COUNTRIES = ("France", "Réunion")


def _get_chart_path():
    return frappe.get_app_path(
        "erpnext_france",
        "regional",
        "france",
        "chart_of_accounts",
    )


def _get_local_charts():
    charts = []
    path = _get_chart_path()

    if not os.path.exists(path):
        return charts

    for filename in os.listdir(path):
        if not filename.endswith(".json"):
            continue

        with open(os.path.join(path, filename), encoding="utf-8") as file:
            content = json.load(file)

        if (
            content.get("disabled", "No") == "No"
            or frappe.local.flags.allow_unverified_charts
        ):
            charts.append(content["name"])

    return charts


@frappe.whitelist()
def get_charts_for_country_fr(country, with_standard=False):
    if country not in SUPPORTED_COUNTRIES:
        return erpnext_get_charts_for_country(country, with_standard)

    charts = _get_local_charts()

    if len(charts) != 1 or with_standard:
        charts += ["Standard", "Standard with Numbers"]

    return charts


@frappe.whitelist()
def get_chart_fr(chart_template, existing_company=None):
    if existing_company:
        return get_account_tree_from_existing_company(existing_company)

    path = _get_chart_path()

    if os.path.exists(path):
        for filename in os.listdir(path):
            if not filename.endswith(".json"):
                continue

            with open(os.path.join(path, filename), encoding="utf-8") as file:
                content = json.load(file)

            if content.get("name") == chart_template:
                return content.get("tree")

    return erpnext_get_chart(chart_template, existing_company)