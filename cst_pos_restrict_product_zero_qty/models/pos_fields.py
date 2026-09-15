# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class PosConfig(models.Model):
	_inherit = "pos.config"

	prod_zero_qty_restrict = fields.Boolean(string='Restrict Zero Quantity')


class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	pos_prod_zero_qty_restrict = fields.Boolean(related="pos_config_id.prod_zero_qty_restrict", readonly=False)
