# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    interbranch_account_id = fields.Many2one(
        'account.account',
        string='Inter-Company Stocks Account',
        company_dependent=True,
        help=(
            "Default clearing account for inter-company/branch stock transfers. "
            "Set this once per company and it will pre-fill on every new transfer.\n\n"
            "Source (stock out):  Dr Interbranch  /  Cr Stock Valuation\n"
            "Branch (stock in):   Dr Stock Valuation  /  Cr Interbranch\n\n"
            "The balance on this account equals the value of stock in transit."
        ),
    )
