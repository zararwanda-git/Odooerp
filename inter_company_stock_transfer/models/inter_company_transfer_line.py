# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InterCompanyTransferLine(models.Model):
    _name = 'inter.company.transfer.line'
    _description = 'Inter-Company Transfer Line'

    transfer_id = fields.Many2one(
        'inter.company.transfer',
        string='Transfer',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('type', 'in', ['product', 'consu'])]",
    )
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
    )
    available_qty = fields.Float(
        string='On Hand (Source)',
        compute='_compute_available_qty',
        digits='Product Unit of Measure',
    )
    note = fields.Char(string='Note')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id

    @api.depends('product_id', 'transfer_id.source_location_id')
    def _compute_available_qty(self):
        for line in self:
            if line.product_id and line.transfer_id.source_location_id:
                line.available_qty = line.product_id.with_context(
                    location=line.transfer_id.source_location_id.id
                ).qty_available
            else:
                line.available_qty = 0.0

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise UserError(_('Quantity must be greater than zero.'))