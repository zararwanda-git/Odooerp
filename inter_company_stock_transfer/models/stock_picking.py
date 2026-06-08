# -*- coding: utf-8 -*-
import logging
from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """
        After validation, check if this picking belongs to an inter-company
        transfer and trigger the appropriate next step automatically:

        SOURCE picking validated by user selecting serials:
          → post source journal entry (Dr Interbranch / Cr Stock Valuation)
          → create destination picking
          → notify branch users

        DESTINATION picking validated by branch:
          → trigger action_mark_received() to fix move value and post
            destination journal entry (Dr Stock Valuation / Cr Interbranch)

        The _ict_validating context flag is set when action_mark_received()
        calls button_validate() internally. We skip the destination trigger
        in that case to prevent action_mark_received() running twice, which
        would produce two identical journal entries.
        """
        res = super().button_validate()

        # --- SOURCE picking trigger ---
        # The user has selected serials and validated the source picking.
        # Find the confirmed transfer waiting for this picking to be done.
        # Skip if _ict_validating is set (we are inside action_mark_received).
        if not self.env.context.get('_ict_validating'):
            source_transfers = self.env['inter.company.transfer'].sudo().search([
                ('source_picking_id', 'in', self.ids),
                ('state', '=', 'confirmed'),
                ('destination_picking_id', '=', False),
            ])
            for transfer in source_transfers:
                if transfer.source_picking_id.state == 'done':
                    _logger.info(
                        '[ICT] source picking %s validated — triggering '
                        '_on_source_picking_validated for transfer %s',
                        transfer.source_picking_id.name, transfer.name,
                    )
                    transfer._on_source_picking_validated()

        # --- DESTINATION picking trigger ---
        # Skip if we are already inside action_mark_received() — that method
        # set this flag before calling button_validate() to prevent this
        # override from triggering a second execution.
        if not self.env.context.get('_ict_validating'):
            dest_transfers = self.env['inter.company.transfer'].sudo().search([
                ('destination_picking_id', 'in', self.ids),
                ('state', '=', 'confirmed'),
            ])
            for transfer in dest_transfers:
                if transfer.destination_picking_id.state == 'done':
                    _logger.info(
                        '[ICT] dest picking %s validated — triggering '
                        'action_mark_received for transfer %s',
                        transfer.destination_picking_id.name, transfer.name,
                    )
                    transfer.action_mark_received()

        return res