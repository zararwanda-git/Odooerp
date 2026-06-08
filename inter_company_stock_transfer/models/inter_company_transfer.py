# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class InterCompanyTransfer(models.Model):
    _name = 'inter.company.transfer'
    _description = 'Inter-Company Stock Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    source_company_id = fields.Many2one('res.company', string='Source Company', required=True,
                                        domain=lambda self: [('id', 'in', self.env.companies.ids)],
                                        default=lambda self: self.env.company)
    destination_company_id = fields.Many2one('res.company', string='Destination Company',
                                             required=True,
                                             domain=lambda self: [('id', 'in', self.env.companies.ids)])

    source_warehouse_id = fields.Many2one('stock.warehouse', string='Source Warehouse', required=True)
    destination_warehouse_id = fields.Many2one('stock.warehouse', string='Destination Warehouse', required=True)
    source_location_id = fields.Many2one('stock.location', string='Source Location', required=True,
                                         domain="[('usage','=','internal'),('company_id','=',source_company_id)]")
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', required=True,
                                              domain="[('usage','=','internal'),('company_id','=',destination_company_id)]")

    interbranch_account_id = fields.Many2one(
        'account.account', string='Inter-Company Stocks Account', required=True,
        help=(
            "Clearing account used on both sides.\n\n"
            "Stock out:  Dr Interbranch  /  Cr Stock Valuation\n"
            "Stock in:   Dr Stock Valuation  /  Cr Interbranch\n\n"
            "Balance = stock currently in transit. Nets to zero on receipt."
        ),
    )

    transfer_date = fields.Datetime(string='Transfer Date', default=fields.Datetime.now, required=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', default=fields.Datetime.now)

    line_ids = fields.One2many('inter.company.transfer.line', 'transfer_id',
                               string='Transfer Lines', copy=True)

    source_picking_id = fields.Many2one('stock.picking', string='Source Picking',
                                        readonly=True, copy=False)
    destination_picking_id = fields.Many2one('stock.picking', string='Destination Picking',
                                             readonly=True, copy=False)
    source_move_id = fields.Many2one('account.move', string='Source Journal Entry',
                                     readonly=True, copy=False)
    destination_move_id = fields.Many2one('account.move', string='Destination Journal Entry',
                                          readonly=True, copy=False)

    note = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # ------------------------------------------------------------------ #
    #  Onchanges                                                           #
    # ------------------------------------------------------------------ #

    @api.onchange('source_company_id')
    def _onchange_source_company_id(self):
        self.source_warehouse_id = False
        self.source_location_id = False
        if self.source_company_id:
            wh = self.env['stock.warehouse'].search(
                [('company_id', '=', self.source_company_id.id)], limit=1)
            self.source_warehouse_id = wh
            if wh:
                self.source_location_id = wh.lot_stock_id
            account = self.source_company_id.with_company(
                self.source_company_id).interbranch_account_id
            if account:
                self.interbranch_account_id = account

    @api.onchange('destination_company_id')
    def _onchange_destination_company_id(self):
        self.destination_warehouse_id = False
        self.destination_location_id = False
        if self.destination_company_id:
            wh = self.env['stock.warehouse'].search(
                [('company_id', '=', self.destination_company_id.id)], limit=1)
            self.destination_warehouse_id = wh
            if wh:
                self.destination_location_id = wh.lot_stock_id

    @api.onchange('source_warehouse_id')
    def _onchange_source_warehouse_id(self):
        if self.source_warehouse_id:
            self.source_location_id = self.source_warehouse_id.lot_stock_id

    @api.onchange('destination_warehouse_id')
    def _onchange_destination_warehouse_id(self):
        if self.destination_warehouse_id:
            self.destination_location_id = self.destination_warehouse_id.lot_stock_id

    # ------------------------------------------------------------------ #
    #  Constraints & CRUD                                                  #
    # ------------------------------------------------------------------ #

    @api.constrains('source_company_id', 'destination_company_id')
    def _check_companies_differ(self):
        for rec in self:
            if rec.source_company_id == rec.destination_company_id:
                raise ValidationError(_('Source and destination companies must be different.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'inter.company.transfer') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    def _check_product_quantities(self):
        for line in self.line_ids:
            available = line.product_id.with_context(
                location=self.source_location_id.id
            ).qty_available
            if line.quantity > available:
                raise UserError(_(
                    "Insufficient stock for '%(product)s'.\n"
                    "On Hand: %(avail)s  |  Requested: %(req)s",
                    product=line.product_id.display_name,
                    avail=available, req=line.quantity,
                ))

    def _check_warehouse_settings(self):
        if self.source_location_id.company_id != self.source_company_id:
            raise UserError(_(
                "Source location '%s' does not belong to '%s'.",
                self.source_location_id.complete_name, self.source_company_id.name,
            ))
        if self.destination_location_id.company_id != self.destination_company_id:
            raise UserError(_(
                "Destination location '%s' does not belong to '%s'.",
                self.destination_location_id.complete_name, self.destination_company_id.name,
            ))

    def _check_accounting_settings(self):
        if not self.interbranch_account_id:
            raise UserError(_("Please set the 'Inter-Company Stocks Account' before confirming."))
        for line in self.line_ids:
            categ = line.product_id.categ_id
            for company in [self.source_company_id, self.destination_company_id]:
                categ_co = categ.with_company(company)
                if categ_co.property_valuation == 'real_time':
                    if not categ_co.property_stock_valuation_account_id:
                        raise UserError(_(
                            "Stock Valuation Account not set for category '%s' in company '%s'.",
                            categ.name, company.name,
                        ))

    # ------------------------------------------------------------------ #
    #  Picking creation                                                    #
    # ------------------------------------------------------------------ #

    def _get_picking_type(self, warehouse, code):
        return self.env['stock.picking.type'].sudo().search([
            ('warehouse_id', '=', warehouse.id),
            ('code', '=', code),
        ], limit=1)

    def _create_source_picking(self):
        picking_type = self._get_picking_type(self.source_warehouse_id, 'internal')
        _logger.info('[ICT] source picking_type: %s (code: %s)',
                     picking_type.name if picking_type else 'NOT FOUND',
                     picking_type.code if picking_type else 'N/A')
        if not picking_type:
            picking_type = self._get_picking_type(self.source_warehouse_id, 'outgoing')
            _logger.warning('[ICT] No internal picking type found for %s, falling back to outgoing',
                            self.source_warehouse_id.name)
        transit = self.env.ref('stock.stock_location_inter_wh', raise_if_not_found=False)
        if not transit:
            transit = self.env['stock.location'].sudo().search(
                [('usage', '=', 'transit'), ('company_id', '=', False)], limit=1)
        dest_loc = transit.id if transit else self.source_location_id.id
        moves = []
        for line in self.line_ids:
            moves.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': self.source_location_id.id,
                'location_dest_id': dest_loc,
                'company_id': self.source_company_id.id,
            }))
        picking = self.env['stock.picking'].sudo().with_company(
            self.source_company_id
        ).create({
            'picking_type_id': picking_type.id,
            'partner_id': self.destination_company_id.partner_id.id,
            'location_id': self.source_location_id.id,
            'location_dest_id': dest_loc,
            'scheduled_date': self.scheduled_date,
            'origin': self.name,
            'company_id': self.source_company_id.id,
            'move_ids': moves,
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _collect_lots_from_source(self, source_picking):
        lots_by_product = {}
        for ml in source_picking.move_line_ids:
            if ml.lot_id:
                lots_by_product.setdefault(ml.product_id.id, []).append({
                    'lot_id': ml.lot_id.id,
                    'qty': ml.quantity,
                })
        return lots_by_product

    def _create_destination_picking(self):
        """
        Create the destination picking using INTERNAL picking type.

        We intentionally keep this as internal (not incoming) to avoid the
        serial number conflict error — Odoo raises 'already reserved' when an
        incoming picking tries to reserve serials that already exist in the
        system from the original supplier receipt.

        Value is injected AFTER validation via _fix_destination_svl() which
        uses the product.value manual override — sitting at position #1 in
        Odoo's _get_value_data() waterfall — to force the correct cost
        (Standard / AVCO / FIFO — per product category) onto the destination
        move records.
        """
        picking_type = self._get_picking_type(self.destination_warehouse_id, 'internal')
        _logger.info('[ICT] dest picking_type: %s (code: %s)',
                     picking_type.name if picking_type else 'NOT FOUND',
                     picking_type.code if picking_type else 'N/A')
        if not picking_type:
            picking_type = self._get_picking_type(self.destination_warehouse_id, 'incoming')
            _logger.warning('[ICT] No internal picking type found for %s, falling back to incoming',
                            self.destination_warehouse_id.name)
        transit = self.env.ref('stock.stock_location_inter_wh', raise_if_not_found=False)
        if not transit:
            transit = self.env['stock.location'].sudo().search(
                [('usage', '=', 'transit'), ('company_id', '=', False)], limit=1)
        src_loc = transit.id if transit else self.destination_location_id.id
        moves = []
        for line in self.line_ids:
            cost = self._get_transfer_unit_cost(line.product_id, line.quantity)
            moves.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'product_uom_qty': line.quantity,
                'price_unit': cost,
                'location_id': src_loc,
                'location_dest_id': self.destination_location_id.id,
                'company_id': self.destination_company_id.id,
            }))
        picking = self.env['stock.picking'].sudo().with_company(
            self.destination_company_id
        ).create({
            'picking_type_id': picking_type.id,
            'partner_id': self.source_company_id.partner_id.id,
            'location_id': src_loc,
            'location_dest_id': self.destination_location_id.id,
            'scheduled_date': self.scheduled_date,
            'origin': self.name,
            'company_id': self.destination_company_id.id,
            'move_ids': moves,
        })
        picking.action_confirm()
        return picking

    # ------------------------------------------------------------------ #
    #  Journal entry creation                                              #
    # ------------------------------------------------------------------ #

    def _get_product_stock_account(self, product, company):
        account = product.categ_id.with_company(company).property_stock_valuation_account_id
        if not account:
            raise UserError(_(
                "No Stock Valuation Account found for product '%s' in company '%s'. "
                "Configure it under Inventory > Configuration > Product Categories.",
                product.display_name, company.name,
            ))
        return account

    def _get_stock_journal(self, company=None):
        Journal = self.env['account.journal'].sudo()
        company = company or self.source_company_id

        companies_to_try = [company]
        if company.parent_id and company.parent_id not in companies_to_try:
            companies_to_try.append(company.parent_id)
        main_company = self.env['res.company'].sudo().search([], order='id asc', limit=1)
        if main_company not in companies_to_try:
            companies_to_try.append(main_company)

        for co in companies_to_try:
            for domain in [
                [('company_id', '=', co.id), ('code', 'ilike', 'STJ')],
                [('company_id', '=', co.id), ('type', 'in', ['general', 'miscellaneous'])],
                [('company_id', '=', co.id)],
            ]:
                journal = Journal.search(domain, limit=1)
                if journal:
                    return journal

        raise UserError(_(
            "No journal found for company '%s' or its parent. "
            "Please configure at least one accounting journal on the parent company.",
            company.name,
        ))

    def _build_line_values(self):
        lines = []
        for line in self.line_ids:
            cost = self._get_transfer_unit_cost(line.product_id, line.quantity)
            lines.append({
                'product': line.product_id,
                'quantity': line.quantity,
                'uom': line.product_uom_id.name,
                'value': cost * line.quantity,
            })
        return lines

    def _create_source_journal_entry(self, line_values):
        """
        Dr  Inter-Company Stocks    $value   (branch owes us this)
        Cr  Stock Valuation         $value   (stock leaves our books)
        """
        journal = self._get_stock_journal()
        move_lines = []
        for lv in line_values:
            label = _('%(ref)s | %(product)s × %(qty)s %(uom)s → %(dest)s',
                      ref=self.name, product=lv['product'].display_name,
                      qty=lv['quantity'], uom=lv['uom'],
                      dest=self.destination_company_id.name)
            stock_account = self._get_product_stock_account(lv['product'], self.source_company_id)
            move_lines += [
                (0, 0, {'name': label, 'account_id': self.interbranch_account_id.id,
                        'debit': lv['value'], 'credit': 0.0,
                        'company_id': self.source_company_id.id}),
                (0, 0, {'name': label, 'account_id': stock_account.id,
                        'debit': 0.0, 'credit': lv['value'],
                        'company_id': self.source_company_id.id}),
            ]
        move = self.env['account.move'].sudo().with_company(self.source_company_id).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.transfer_date,
            'ref': _('%(name)s — stock out to %(dest)s',
                     name=self.name, dest=self.destination_company_id.name),
            'company_id': self.source_company_id.id,
            'line_ids': move_lines,
        })
        move.action_post()
        return move

    def _create_destination_journal_entry(self, line_values):
        """
        Dr  Stock Valuation         $value   (stock enters branch books)
        Cr  Inter-Company Stocks    $value   (clears the source debit — nets to zero)
        """
        journal = self._get_stock_journal(company=self.destination_company_id)
        move_lines = []
        for lv in line_values:
            label = _('%(ref)s | %(product)s × %(qty)s %(uom)s ← %(src)s',
                      ref=self.name, product=lv['product'].display_name,
                      qty=lv['quantity'], uom=lv['uom'],
                      src=self.source_company_id.name)
            stock_account = self._get_product_stock_account(lv['product'], self.destination_company_id)
            move_lines += [
                (0, 0, {'name': label, 'account_id': stock_account.id,
                        'debit': lv['value'], 'credit': 0.0,
                        'company_id': self.destination_company_id.id}),
                (0, 0, {'name': label, 'account_id': self.interbranch_account_id.id,
                        'debit': 0.0, 'credit': lv['value'],
                        'company_id': self.destination_company_id.id}),
            ]
        move = self.env['account.move'].sudo().with_company(self.destination_company_id).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.transfer_date,
            'ref': _('%(name)s — stock in from %(src)s',
                     name=self.name, src=self.source_company_id.name),
            'company_id': self.destination_company_id.id,
            'line_ids': move_lines,
        })
        move.action_post()
        return move

    # ------------------------------------------------------------------ #
    #  Unit cost helper — respects product category costing method        #
    # ------------------------------------------------------------------ #

    def _get_transfer_unit_cost(self, product, quantity):
        """
        Return the correct unit cost for a product being transferred from
        the source company, respecting the product category costing method.

        Odoo 19 removed stock.valuation.layer. All three costing methods
        now operate directly on stock.move records:

          Standard  → standard_price directly
          AVCO      → _run_average_batch() — weighted average across all moves
          FIFO      → _run_fifo(qty) — consumes the FIFO stack for exactly
                      this quantity, oldest layers first

        Falls back to standard_price on any error so the transfer always
        completes, with a warning logged for investigation.
        """
        product_in_source = product.with_company(self.source_company_id).sudo()
        cost_method = product_in_source.cost_method

        _logger.info(
            '[ICT] _get_transfer_unit_cost | product: %s | company: %s | '
            'cost_method: %s | quantity: %s',
            product.display_name, self.source_company_id.name,
            cost_method, quantity,
        )

        try:
            if cost_method == 'standard':
                cost = product_in_source.standard_price
                _logger.info('[ICT] standard cost | product: %s | cost: %s',
                             product.display_name, cost)
                return cost

            elif cost_method == 'average':
                std_prices, _total_values = product_in_source._run_average_batch(
                    force_recompute=True
                )
                cost = std_prices.get(product_in_source.id, product_in_source.standard_price)
                _logger.info('[ICT] AVCO cost | product: %s | cost: %s',
                             product.display_name, cost)
                return cost

            else:  # fifo
                total_fifo_value = product_in_source._run_fifo(quantity)
                cost = total_fifo_value / quantity if quantity else product_in_source.standard_price
                _logger.info('[ICT] FIFO cost | product: %s | qty: %s | total: %s | unit: %s',
                             product.display_name, quantity, total_fifo_value, cost)
                return cost

        except Exception as e:
            fallback = product_in_source.standard_price
            _logger.warning(
                '[ICT] _get_transfer_unit_cost error for %s (method: %s): %s '
                '— falling back to standard_price: %s',
                product.display_name, cost_method, e, fallback,
            )
            return fallback

    # ------------------------------------------------------------------ #
    #  Destination value correction                                        #
    # ------------------------------------------------------------------ #

    def _fix_destination_svl(self):
        """
        Fix the destination move value and cancel Odoo's auto journal entry
        so _create_destination_journal_entry() is the only posting.

        THE DOUBLE-POSTING PROBLEM
        --------------------------
        When button_validate() runs on the destination picking, Odoo's
        _action_done() calls _set_value() which internally calls
        _create_account_move() for real_time (perpetual) valuation products.
        This auto-posts a journal entry BEFORE we return from button_validate().

        The previous version of this method then called _set_value() again —
        triggering a SECOND auto journal entry. Combined with
        _create_destination_journal_entry() in action_mark_received(), this
        resulted in two entries on the destination side.

        THE FIX
        -------
        1. Cancel Odoo's auto entry via move.account_move_id.
           Reset to draft then cancel. Our _create_destination_journal_entry()
           in action_mark_received() becomes the single authoritative posting.

        2. Write move.value directly — NO _set_value() call.
           _set_value() triggers _create_account_move() again internally.
           Direct write is safe: remaining_value is computed from
           value * (remaining_qty / quantity) and updates automatically.

        3. Create a product.value override record.
           Sits at position #1 in _get_value_data() waterfall — checked
           before invoices, PO lines, or standard_price. Persists the correct
           cost so any future recompute uses our value not zero.

        4. Sync standard_price on the destination product so future outgoing
           moves (sales, deliveries) use the correct cost and show accurate
           margins.
        """
        if 'product.value' not in self.env.registry:
            _logger.warning('[ICT] product.value not in registry — skipping value fix')
            return

        ProductValue = self.env['product.value'].sudo()

        for move in self.destination_picking_id.move_ids:
            qty_done = sum(move.move_line_ids.mapped('quantity'))
            source_cost = self._get_transfer_unit_cost(move.product_id, qty_done)

            if not source_cost:
                _logger.warning(
                    '[ICT] _fix_destination_svl | source_cost is 0 for %s — skipping',
                    move.product_id.display_name,
                )
                continue

            total_value = source_cost * qty_done

            _logger.info(
                '[ICT] _fix_destination_svl | move: %s | product: %s | '
                'qty_done: %s | unit_cost: %s | total_value: %s',
                move.id, move.product_id.display_name,
                qty_done, source_cost, total_value,
            )

            # Step 1 — Cancel Odoo's auto-posted journal entry.
            # Odoo posts this inside _action_done() → _create_account_move()
            # for real_time valuation products during button_validate().
            # We cancel it so _create_destination_journal_entry() is the
            # only entry on the destination side.
            auto_move = move.sudo().account_move_id
            if auto_move and auto_move.state == 'posted':
                _logger.info(
                    '[ICT] cancelling Odoo auto dest entry %s for move %s',
                    auto_move.name, move.id,
                )
                try:
                    auto_move.sudo().button_draft()
                    auto_move.sudo().button_cancel()
                    _logger.info('[ICT] cancelled %s successfully', auto_move.name)
                except Exception as e:
                    _logger.warning(
                        '[ICT] could not cancel auto entry %s: %s — '
                        'double posting may still occur, investigate manually',
                        auto_move.name, e,
                    )

            # Step 2 — Write move.value directly. NO _set_value() call.
            # _set_value() triggers _create_account_move() again internally
            # which would post yet another journal entry.
            move.sudo().write({'value': total_value})
            _logger.info(
                '[ICT] wrote move.value | move: %s | value: %s',
                move.id, total_value,
            )

            # Step 3 — Create product.value override (position #1 in waterfall).
            # _get_manual_value() is checked before invoices, PO lines,
            # standard_price. Persists the correct cost for all future recomputes.
            ProductValue.create({
                'move_id': move.id,
                'product_id': move.product_id.id,
                'value': total_value,
                'company_id': self.destination_company_id.id,
                'description': _(
                    'Inter-branch receipt from %(src)s | %(ref)s',
                    src=self.source_company_id.name,
                    ref=self.name,
                ),
            })
            _logger.info(
                '[ICT] product.value created for move %s | value: %s',
                move.id, total_value,
            )

            # Step 4 — Sync standard_price on destination product
            # so future deliveries and sales from the branch use the
            # correct cost and show accurate margins.
            move.product_id.with_company(
                self.destination_company_id
            ).sudo().write({'standard_price': source_cost})
            _logger.info(
                '[ICT] standard_price updated | product: %s | company: %s | cost: %s',
                move.product_id.display_name,
                self.destination_company_id.name,
                source_cost,
            )

    # ------------------------------------------------------------------ #
    #  Notifications                                                       #
    # ------------------------------------------------------------------ #

    def _notify_destination_users(self):
        dest_users = self.env['res.users'].sudo().search([
            ('company_ids', 'in', self.destination_company_id.id),
            ('share', '=', False),
        ], limit=5)
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        for user in dest_users:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                summary=_('Inter-Branch Stock Receipt Required'),
                note=_(
                    "Transfer <b>%(name)s</b> from <b>%(src)s</b> is awaiting receipt. "
                    "Open picking <b>%(picking)s</b> in Inventory → Receipts and validate it.",
                    name=self.name, src=self.source_company_id.name,
                    picking=self.destination_picking_id.name,
                ),
                user_id=user.id,
            )

    # ------------------------------------------------------------------ #
    #  Actions                                                             #
    # ------------------------------------------------------------------ #

    def action_confirm(self):
        """
        Validate settings and create the source picking in a ready-to-pick
        state so the user can open it, select the exact serial numbers they
        want to transfer, and validate it directly on the picking.

        When the source picking is validated, StockPicking.button_validate()
        detects it is the source picking of a confirmed inter-company transfer
        and automatically:
          - posts the source journal entry (Dr Interbranch / Cr Stock Valuation)
          - creates the destination picking
          - notifies branch users

        The transfer then moves to state=confirmed and waits for the branch
        to receive and validate the destination picking, which triggers
        action_mark_received() via the same StockPicking override.
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line before confirming.'))

        self._check_warehouse_settings()
        self._check_product_quantities()
        self._check_accounting_settings()

        # Create source picking and reserve stock so serials are suggested.
        # Do NOT validate — the user selects serials on the picking directly.
        source_picking = self._create_source_picking()

        self.write({
            'state': 'confirmed',
            'source_picking_id': source_picking.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _on_source_picking_validated(self):
        """
        Triggered by StockPicking.button_validate() when the user validates
        the source picking after selecting serial numbers.

        Posts the source journal entry and creates the destination picking.
        The transfer stays in state=confirmed, waiting for the branch to
        receive the stock and trigger action_mark_received().
        """
        self.ensure_one()
        _logger.info(
            '[ICT] _on_source_picking_validated | transfer: %s',
            self.name,
        )

        line_values = self._build_line_values()
        source_move = self._create_source_journal_entry(line_values)
        dest_picking = self._create_destination_picking()

        self.write({
            'destination_picking_id': dest_picking.id,
            'source_move_id': source_move.id,
        })

        self._notify_destination_users()
        _logger.info(
            '[ICT] source validated | source JE: %s | dest picking: %s',
            source_move.name, dest_picking.name,
        )

    def action_mark_received(self):
        """
        1. Validate destination picking
           (Odoo auto-posts a JE inside button_validate for real_time products)
        2. _fix_destination_svl() cancels that auto JE + fixes move.value
           + creates product.value override + syncs standard_price
        3. Post our single correct destination JE
        """
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed transfers can be marked as received.'))

        # Re-entrancy guard — prevents double execution if a stock.picking
        # override or automated action calls action_mark_received again within
        # the same transaction (triggered by button_validate on dest picking).
        # Both entries get the same reference so it's the only sign of the bug.
        ctx_key = '_ict_mark_received_%s' % self.id
        if self.env.context.get(ctx_key):
            _logger.warning('[ICT] action_mark_received re-entered for %s — skipping', self.name)
            return
        self = self.with_context(**{ctx_key: True})

        _logger.info(
            '[ICT] action_mark_received | transfer: %s | '
            'dest picking: %s | dest picking state: %s',
            self.name,
            self.destination_picking_id.name,
            self.destination_picking_id.state,
        )

        if self.destination_picking_id.state != 'done':
            _logger.info('[ICT] calling button_validate on %s',
                         self.destination_picking_id.name)
            self.destination_picking_id.with_company(
                self.destination_company_id
            ).with_context(_ict_validating=True).button_validate()
            _logger.info('[ICT] button_validate done | picking state now: %s',
                         self.destination_picking_id.state)
        else:
            _logger.info('[ICT] picking already done — skipping validate, running SVL fix only')

        # Cancels Odoo's auto entry + writes move.value + creates product.value
        # + syncs standard_price. Does NOT post any journal entry itself.
        self._fix_destination_svl()

        # Post the single correct destination journal entry.
        line_values = self._build_line_values()
        dest_move = self._create_destination_journal_entry(line_values)

        self.write({'state': 'received', 'destination_move_id': dest_move.id})
        self.activity_ids.action_done()
        self.message_post(body=_(
            "Stock received by <b>%(dest)s</b>. "
            "Interbranch account cleared. Journal entry: <b>%(jnl)s</b>",
            dest=self.destination_company_id.name, jnl=dest_move.name,
        ))

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'received':
            raise UserError(_('Cannot cancel a completed transfer.'))
        for picking in [self.source_picking_id, self.destination_picking_id]:
            if picking and picking.state not in ('done', 'cancel'):
                picking.action_cancel()
        for move in [self.source_move_id, self.destination_move_id]:
            if move and move.state == 'posted':
                move.button_cancel()
        self.write({'state': 'cancelled'})

    def action_view_source_picking_to_validate(self):
        """Open the source picking so the user can select serial numbers."""
        return self._open_record('stock.picking', self.source_picking_id.id)

    def action_reset_draft(self):
        self.ensure_one()
        if self.state != 'cancelled':
            raise UserError(_('Only cancelled transfers can be reset to draft.'))
        self.write({'state': 'draft'})

    def _open_record(self, model, res_id):
        return {'type': 'ir.actions.act_window', 'res_model': model,
                'res_id': res_id, 'view_mode': 'form', 'target': 'current'}

    def action_view_source_picking(self):
        return self._open_record('stock.picking', self.source_picking_id.id)

    def action_view_destination_picking(self):
        return self._open_record('stock.picking', self.destination_picking_id.id)

    def action_view_source_move(self):
        return self._open_record('account.move', self.source_move_id.id)

    def action_view_destination_move(self):
        return self._open_record('account.move', self.destination_move_id.id)