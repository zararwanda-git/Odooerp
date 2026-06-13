from odoo import models, fields, api, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    is_internal_transfer = fields.Boolean(
        string="Internal Transfer",
        default=False,
    )
    destination_journal_id = fields.Many2one(
        'account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('id', '!=', journal_id)]",
        check_company=True,
    )
    paired_internal_transfer_payment_id = fields.Many2one(
        'account.payment',
        string="Paired Payment",
        copy=False,
        readonly=True,
    )

    @api.onchange('is_internal_transfer')
    def _onchange_is_internal_transfer(self):
        for rec in self:
            if rec.is_internal_transfer:
                rec.partner_id = rec.company_id.partner_id
            else:
                rec.destination_journal_id = False

    def _compute_destination_account_id(self):
        """
        Force internal transfers to use the liquidity transfer account
        configured in Accounting > Configuration > Settings.

        In Odoo 19 the base method no longer reads transfer_account_id
        automatically and falls back to receivable/payable (e.g. 1510).
        We override here to restore the correct behaviour.
        """
        super()._compute_destination_account_id()
        for pay in self:
            if not pay.is_internal_transfer:
                continue
            # transfer_account_id is set under:
            # Accounting > Configuration > Settings > Default Accounts
            # > Liquidity Transfer Account
            transfer_account = pay.company_id.transfer_account_id
            if transfer_account:
                pay.destination_account_id = transfer_account
            # If not configured fall back to whatever super() set —
            # user will see the wrong account and know to configure it

    def action_post(self):
        res = super().action_post()
        for pay in self:
            if (
                pay.is_internal_transfer
                and pay.destination_journal_id
                and not pay.paired_internal_transfer_payment_id
            ):
                memo = (
                    getattr(pay, 'memo', None)
                    or getattr(pay, 'narration', None)
                    or getattr(pay, 'ref', None)
                    or _('Internal Transfer from %s', pay.journal_id.name)
                )
                paired_pay = self.create({
                    'date': pay.date,
                    'amount': pay.amount,
                    'payment_type': 'inbound' if pay.payment_type == 'outbound' else 'outbound',
                    'partner_type': pay.partner_type,
                    'memo': memo,
                    'journal_id': pay.destination_journal_id.id,
                    'destination_journal_id': pay.journal_id.id,
                    'partner_id': pay.partner_id.id,
                    'is_internal_transfer': True,
                    'paired_internal_transfer_payment_id': pay.id,
                })
                paired_pay.action_post()
                pay.paired_internal_transfer_payment_id = paired_pay.id
        return res