# -*- coding: utf-8 -*-
{
    "name": "Internal Transfer Landed Cost",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Apply landed costs to internal transfers with safe SVL adjustments",
    "description": """
Internal Transfer Landed Cost
=============================
Extends Odoo's native Landed Costs to support internal warehouse transfers.
Safe SVL adjustments, automatic journal entries, FIFO & AVCO compatible.
""",
    "author": "Arcivo",
    "website": "https://arcivo.odoo.com/",
    "license": "OPL-1",
    "depends": [
        "stock_landed_costs",
    ],
    "data": [
        "views/stock_landed_cost_views.xml",
        "views/stock_picking_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "price": 40,
    "currency": "EUR",
    "installable": True,
    "application": False,
    "auto_install": False,
}
