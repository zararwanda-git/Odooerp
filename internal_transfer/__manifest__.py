# -*- coding: utf-8 -*-
{
    'name': 'Internal Transfer Workflow',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Internal bank/cash transfers with paired journal entries',
    'description': """
Internal Transfer Workflow
==========================
Extends account.payment to support internal transfers between
bank and cash journals within the same company.

Features:
---------
* Internal Transfer checkbox on the payment form
* Destination Journal field (visible only when transfer is enabled)
* Paired payment automatically created in the destination journal on posting
* Liquidity Transfer Account used for both legs (from company settings)
* Internal transfers excluded from Customer/Vendor payment filters
* Dedicated Internal Transfers filter in the payment search view
    """,
    'author': 'GlobX',
    'website': 'https://www.theglobx.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}