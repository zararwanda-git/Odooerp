# -*- coding: utf-8 -*-
{
    "name": "POS Zero Quantity Restriction",
    "summary": "Restricts adding zero-quantity items in POS by showing a warning popup.",
    "description": """
        This module adds a validation in the Odoo Point of Sale to prevent adding 
        any item with zero available quantity. If an item has no stock, the POS 
        displays a warning popup and blocks the action.

        Key Features:
        - Detects zero-quantity items in POS.
        - Prevents adding them to the order.
        - Shows a clear warning popup to the cashier.
        - Lightweight and reliable POS safety enhancement.
    """,
    "author": "CodeSphere Tech",
    "website": "https://www.codespheretech.in/",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "sequence": 0,
    "currency": "USD",
    "price": "0",
    "depends": ["point_of_sale", ],
    "data": [
        'views/res_config_views.xml',
    ],
    "assets": {
        'point_of_sale._assets_pos': [
            'cst_pos_restrict_product_zero_qty/static/src/**/*',
        ],
    },
    "images": ["static/description/Banner.png"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
