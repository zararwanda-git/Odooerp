# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def get_valuation_lines(self):
        self.ensure_one()
        if not any(p.picking_type_id.code == 'internal' for p in self.picking_ids):
            return super().get_valuation_lines()

        lines = []
        for move in self._get_targeted_move_ids():
            if move.product_id.cost_method not in ('fifo', 'average'):
                continue
            if move.state == 'cancel' or not move.quantity:
                continue
            qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            former_cost = move.product_id.with_company(self.company_id).standard_price * qty
            lines.append({
                'product_id': move.product_id.id,
                'move_id': move.id,
                'quantity': qty,
                'former_cost': former_cost,
                'weight': move.product_id.weight * qty,
                'volume': move.product_id.volume * qty,
            })
        if not lines:
            raise UserError(_("No eligible products found. Products must use FIFO or Average costing."))
        return lines

    def button_validate(self):
        if not any(p.picking_type_id.code == 'internal' for cost in self for p in cost.picking_ids):
            return super().button_validate()

        self._check_can_validate()
        cost_without_adj = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_adj:
            cost_without_adj.compute_landed_cost()
        if not self._check_sum():
            raise UserError(_('Cost and adjustments lines do not match. Recompute the landed costs.'))

        for cost in self:
            cost = cost.with_company(cost.company_id)

            # ── Journal entry ────────────────────────────────────────────────
            move_vals = {
                'journal_id': cost.account_journal_id.id,
                'date': cost.date,
                'ref': cost.name,
                'line_ids': [],
                'move_type': 'entry',
            }
            for line in cost.valuation_adjustment_lines.filtered(lambda l: l.move_id):
                if line.move_id.product_id.valuation != 'real_time':
                    continue
                move_vals['line_ids'] += line._create_accounting_entries(line.quantity)

            cost_vals = {'state': 'done'}
            if move_vals.get('line_ids'):
                acc_move = self.env['account.move'].create(move_vals)
                cost_vals['account_move_id'] = acc_move.id
            cost.write(cost_vals)
            if cost.account_move_id:
                cost.account_move_id._post()

            # ── Value + avg_cost fix ─────────────────────────────────────────
            product_adjustments = {}
            for line in cost.valuation_adjustment_lines.filtered(
                lambda l: l.move_id and l.additional_landed_cost
            ):
                move = line.move_id
                product = move.product_id
                key = product.id

                if key not in product_adjustments:
                    product_adjustments[key] = {
                        'product': product,
                        'total_cost': 0.0,
                        'transferred_qty': line.quantity,
                        'former_cost': line.former_cost,
                        'move': move,
                    }
                product_adjustments[key]['total_cost'] += line.additional_landed_cost

            messages = []
            for key, data in product_adjustments.items():
                product = data['product']
                total_additional = data['total_cost']
                transferred_qty = data['transferred_qty']
                former_cost = data['former_cost']
                move = data['move']
                additional_per_unit = total_additional / transferred_qty

                p = product.with_company(cost.company_id).sudo()
                old_avg = p.standard_price
                on_hand_qty = p.qty_available

                existing_total = old_avg * on_hand_qty
                new_avg = (existing_total + total_additional) / on_hand_qty if on_hand_qty else old_avg + additional_per_unit

                current_move_value = move.sudo().value or 0.0
                if not current_move_value:
                    current_move_value = former_cost
                new_move_value = current_move_value + total_additional

                _logger.info(
                    '[ITLC] | product: %s | transferred_qty: %.2f | '
                    'current_move_value: %.2f | +landed: %.2f | new_move_value: %.2f | '
                    'on_hand: %.2f | old_avg: %.4f | new_avg: %.4f',
                    product.display_name, transferred_qty,
                    current_move_value, total_additional, new_move_value,
                    on_hand_qty, old_avg, new_avg,
                )

                move.sudo().write({'value': new_move_value})

                self.env['product.value'].sudo().with_company(cost.company_id).create({
                    'product_id': product.id,
                    'value': new_avg,
                    'company_id': cost.company_id.id,
                    'description': _(
                        'Landed Cost %(lc)s — avg reset (%(old).4f → %(new).4f)',
                        lc=cost.name, old=old_avg, new=new_avg,
                    ),
                })

                msg = (
                    "Product: %s | Transferred: %.2f | "
                    "Transfer Value: %.2f | +Landed: %.2f | Move Value: %.2f | "
                    "Old Avg: %.4f | New Avg: %.4f"
                ) % (
                    product.display_name, transferred_qty,
                    current_move_value, total_additional, new_move_value,
                    old_avg, new_avg,
                )
                messages.append(msg)

            # ── Inventory valuation display ──────────────────────────────────
            # state is already 'done' so _get_landed_cost() finds the adjustment
            # lines. _set_value() calls _get_value_from_extra() which builds the
            # "Additional landed costs" entry in the inventory valuation view.
            cost.valuation_adjustment_lines.move_id._set_value()

            if messages:
                cost.message_post(
                    body="<b>Product Cost Updated:</b><br/>" + "<br/>".join(messages),
                    message_type='comment',
                )

        return True
