# -*- coding: utf-8 -*-
{
    'name': 'Inter-Company Stock Transfer',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Transfer stock between companies without Sales/Purchase Orders',
    'description': """
Inter-Company Stock Transfer
============================
This module allows you to transfer stock between two companies without
creating Sales Orders (SO) or Purchase Orders (PO).

Features:
---------
* Inter-Company Stock Transfer without SO/PO
* Barcode-based product matching across companies
* Receipt confirmation by destination company
* Automatic accounting entries generation
* Odoo activity notifications for receipt confirmation
* Status tracking: Draft → Confirmed → Done/Received
    """,
    'author': 'GlobX',
    'website': 'https://www.theglobx.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/inter_company_transfer_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
