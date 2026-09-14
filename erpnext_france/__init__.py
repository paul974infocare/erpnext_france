__version__ = "16.0.1"

import erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts as chart_of_accounts

from erpnext_france.erpnext_france.overrides.doctype.chart_of_accounts import get_chart_fr


chart_of_accounts.get_chart = get_chart_fr