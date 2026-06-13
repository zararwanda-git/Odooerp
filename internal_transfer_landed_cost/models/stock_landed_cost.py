# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def _has_internal_pickings(self):
        return any(p.picking_type_id.code == 'internal' for p in self.picking_ids)

    # ------------------------------------------------------------------ #
    #  Valuation lines                                                     #
    # ------------------------------------------------------------------ #

    def get_valuation_lines(self):
        self.ensure_one()
        if not self._has_internal_pickings():
            return super().get_valuation_lines()

        lines = []
        for move in self._get_targeted_move_ids():
            if move.product_id.cost_method not in ('fifo', 'average'):
                continue
            if move.state == 'cancel' or not move.quantity:
                continue
            qty = move.product_uom._compute_quantity(
                move.quantity, move.product_id.uom_id
            )
            # _get_value() returns 0 for internal moves; use standard_price instead.
            former_cost = (
                move.product_id.with_company(self.company_id).standard_price * qty
            )
            lines.append({
                'product_id': move.product_id.id,
                'move_id': move.id,
                'quantity': qty,
                'former_cost': former_cost,
                'weight': move.product_id.weight * qty,
                'volume': move.product_id.volume * qty,
            })

        if not lines:
            raise UserError(_(
                'No eligible products found. '
                'Products must use FIFO or Average costing.'
            ))
        return lines

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    def button_validate(self):
        if not any(self._has_internal_pickings() for cost in self):
            return super().button_validate()

        self._check_can_validate()
        cost_without_adj = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_adj:
            cost_without_adj.compute_landed_cost()
        if not self._check_sum():
            raise UserError(_(
                'Cost and adjustments lines do not match. '
                'Recompute the landed costs.'
            ))

        for cost in self:
            cost = cost.with_company(cost.company_id)
            company = cost.company_id

            adj_lines = cost.valuation_adjustment_lines.filtered(lambda l: l.move_id)
            real_time_lines = adj_lines.filtered(
                lambda l: l.move_id.product_id.categ_id
                .with_company(company).property_valuation == 'real_time'
            )

            # ---- Journal entry ----------------------------------------
            je_line_vals = []
            for line in real_time_lines:
                # Use full quantity — remaining_qty is 0 for internal moves.
                je_line_vals += line._create_accounting_entries(line.quantity)

            acc_move = False
            if je_line_vals:
                acc_move = self.env['account.move'].sudo().with_company(company).create({
                    'journal_id': cost.account_journal_id.id,
                    'date': cost.date,
                    'ref': cost.name,
                    'move_type': 'entry',
                    'line_ids': je_line_vals,
                })
                acc_move._post()

            # ---- Valuation records ------------------------------------
            adj_cost_lines = real_time_lines.filtered(lambda l: l.additional_landed_cost)
            if 'stock.valuation.layer' in self.env.registry:
                SVL = self.env['stock.valuation.layer'].sudo()
                for line in adj_cost_lines:
                    svl_vals = {
                        'company_id': company.id,
                        'product_id': line.move_id.product_id.id,
                        'stock_move_id': line.move_id.id,
                        'quantity': 0.0,
                        'unit_cost': 0.0,
                        'value': line.additional_landed_cost,
                        'remaining_qty': 0.0,
                        'remaining_value': 0.0,
                        'description': _('Landed Cost: %(name)s', name=cost.name),
                        'stock_landed_cost_id': cost.id,
                    }
                    if acc_move:
                        svl_vals['account_move_id'] = acc_move.id
                    SVL.create(svl_vals)
                    _logger.info(
                        '[ITLC] SVL created | product: %s | value: %.2f | move: %s',
                        line.move_id.product_id.display_name,
                        line.additional_landed_cost,
                        line.move_id.id,
                    )
            elif 'product.value' in self.env.registry and adj_cost_lines:
                self.env['product.value'].sudo().create([{
                    'company_id': company.id,
                    'product_id': line.move_id.product_id.id,
                    'value': line.additional_landed_cost,
                    'description': _('Landed Cost: %(name)s', name=cost.name),
                } for line in adj_cost_lines])
                _logger.info('[ITLC] product.value records created for %d lines', len(adj_cost_lines))

            # ---- Average cost update -----------------------------------
            # cost_method is company-dependent in Odoo 19 — must use with_company().
            cost_by_product = {}
            for line in adj_cost_lines.filtered(
                lambda l: l.move_id.product_id.with_company(company).cost_method == 'average'
            ):
                pid = line.move_id.product_id.id
                if pid not in cost_by_product:
                    cost_by_product[pid] = {
                        'product': line.move_id.product_id,
                        'additional': 0.0,
                    }
                cost_by_product[pid]['additional'] += line.additional_landed_cost

            messages = []
            for pid, data in cost_by_product.items():
                product = data['product']
                p = product.with_company(company)
                old_price = p.standard_price

                on_hand_qty = sum(
                    self.env['stock.quant'].sudo().search([
                        ('product_id', '=', product.id),
                        ('location_id.usage', '=', 'internal'),
                        ('company_id', '=', company.id),
                    ]).mapped('quantity')
                )
                if on_hand_qty <= 0:
                    _logger.warning(
                        '[ITLC] on_hand_qty is 0 for %s — skipping price update',
                        product.display_name,
                    )
                    continue

                # new average = (current total value + additional) / on_hand_qty
                new_price = (old_price * on_hand_qty + data['additional']) / on_hand_qty
                p.standard_price = new_price

                msg = (
                    f"{product.display_name} | "
                    f"Old: {old_price:.2f} → New: {new_price:.2f} | "
                    f"Additional: {data['additional']:.2f} | Qty: {on_hand_qty:.2f}"
                )
                messages.append(msg)
                _logger.info('[ITLC] price update | %s', msg)

            # ---- Finalise ---------------------------------------------
            cost_vals = {'state': 'done'}
            if acc_move:
                cost_vals['account_move_id'] = acc_move.id
            cost.write(cost_vals)

            if messages:
                cost.message_post(
                    body='<b>Product Cost Updated:</b><br/>' + '<br/>'.join(messages),
                    message_type='comment',
                )

        return True
