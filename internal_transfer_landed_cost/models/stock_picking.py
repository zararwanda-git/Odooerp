# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    internal_landed_cost_count = fields.Integer(
        string='Landed Cost Count',
        compute='_compute_internal_landed_cost_count',
    )

    def _compute_internal_landed_cost_count(self):
        for picking in self:
            picking.internal_landed_cost_count = self.env[
                'stock.landed.cost'
            ].search_count([('picking_ids', 'in', picking.id)])

    def action_view_landed_costs(self):
        self.ensure_one()
        landed_costs = self.env['stock.landed.cost'].search([
            ('picking_ids', 'in', self.id),
        ])
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Landed Costs'),
            'res_model': 'stock.landed.cost',
            'view_mode': 'list,form',
            'domain': [('id', 'in', landed_costs.ids)],
            'context': {
                'default_picking_ids': [self.id],
            },
        }
        if len(landed_costs) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = landed_costs.id
        return action

    def action_open_new_landed_cost(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Landed Cost'),
            'res_model': 'stock.landed.cost',
            'view_mode': 'form',
            'context': {
                'default_picking_ids': [(6, 0, [self.id])],
            },
            'target': 'current',
        }
