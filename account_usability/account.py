# -*- coding: utf-8 -*-
##############################################################################
#
#    Account Usability module for Odoo
#    Copyright (C) 2015 Akretion (http://www.akretion.com)
#    @author Alexis de Lattre <alexis.delattre@akretion.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp.tools import float_compare
from openerp.exceptions import Warning as UserError


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    origin = fields.Char(track_visibility='onchange')
    supplier_invoice_number = fields.Char(track_visibility='onchange')
    internal_number = fields.Char(track_visibility='onchange')
    reference = fields.Char(track_visibility='onchange')
    sent = fields.Boolean(track_visibility='onchange')
    date_invoice = fields.Date(track_visibility='onchange')
    date_due = fields.Date(track_visibility='onchange')
    payment_term = fields.Many2one(track_visibility='onchange')
    period_id = fields.Many2one(track_visibility='onchange')
    account_id = fields.Many2one(track_visibility='onchange')
    journal_id = fields.Many2one(track_visibility='onchange')
    partner_bank_id = fields.Many2one(track_visibility='onchange')
    fiscal_position = fields.Many2one(track_visibility='onchange')

    @api.multi
    def action_move_create(self):
        res = super(AccountInvoice, self).action_move_create()
        today = fields.Date.context_today(self)
        # When empty, the invoice_date is set by action_move_create()
        for invoice in self:
            if invoice.date_invoice > today:
                raise UserError(_(
                    "You cannot validate the invoice of '%s' "
                    " with an invoice date (%s) in the future !") % (
                        invoice.partner_id.name_get()[0][1],
                        invoice.date_invoice))
            if (
                    not invoice.internal_number and
                    invoice.type in ('out_invoice', 'out_refund')):
                previous_invoices = self.search([
                    ('journal_id', '=', invoice.journal_id.id),
                    ('date_invoice', '!=', False),
                    ('internal_number', '!=', False),
                    ], order='date_invoice desc', limit=1)
                if (
                        previous_invoices and
                        previous_invoices[0].date_invoice >
                        invoice.date_invoice):
                    raise UserError(_(
                        "You cannot validate the invoice for '%s' "
                        "with an invoice date %s because another invoice "
                        "number %s is dated %s in the same journal. "
                        "In order to have a coherent "
                        "invoice number sequence, the date of this invoice "
                        "should the same or a later date as the "
                        "previous one in the same journal.") % (
                            invoice.partner_id.name_get()[0][1],
                            invoice.date_invoice,
                            previous_invoices[0].internal_number,
                            previous_invoices[0].date_invoice,
                            ))
        return res

    @api.multi
    def onchange_payment_term_date_invoice(self, payment_term_id, date_invoice):
        res = super(AccountInvoice, self).onchange_payment_term_date_invoice(
            payment_term_id, date_invoice)
        if res and isinstance(res, dict) and 'value' in res:
            res['value']['period_id'] = False
        return res

    # I really hate to see a "/" in the 'name' field of the account.move.line
    # generated from customer invoices linked to the partners' account because:
    # 1) the label of an account move line is an important field, we can't
    #    write a rubbish '/' in it !
    # 2) the 'name' field of the account.move.line is used in the overdue letter,
    # and '/' is not meaningful for our customer !
    @api.multi
    def action_number(self):
        res = super(AccountInvoice, self).action_number()
        for inv in self:
            if inv.type in ('out_invoice', 'out_refund'):
                self._cr.execute(
                    "UPDATE account_move_line SET name= "
                    "CASE WHEN name='/' THEN %s "
                    "ELSE %s||' - '||name END "
                    "WHERE move_id=%s", (inv.number, inv.number, inv.move_id.id))
                self.invalidate_cache()
        return res


class AccountFiscalYear(models.Model):
    _inherit = 'account.fiscalyear'

    # For companies that have a fiscal year != calendar year
    # I want to be able to write '2015-2016' in the code field
    # => size=9 instead of 6
    code = fields.Char(size=9)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.multi
    def name_get(self):
        if self._context.get('journal_show_code_only'):
            res = []
            for record in self:
                res.append((record.id, record.code))
            return res
        else:
            return super(AccountJournal, self).name_get()


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.multi
    def name_get(self):
        if self._context.get('account_account_show_code_only'):
            res = []
            for record in self:
                res.append((record.id, record.code))
            return res
        else:
            return super(AccountAccount, self).name_get()


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    @api.multi
    def name_get(self):
        if self._context.get('analytic_account_show_code_only'):
            res = []
            for record in self:
                res.append((
                    record.id,
                    record.code or record._get_one_full_name(record)))
            return res
        else:
            return super(AccountAnalyticAccount, self).name_get()


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('date')
    def date_onchange(self):
        if self.date:
            self.period_id = self.env['account.period'].find(self.date)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('credit')
    def _credit_onchange(self):
        if self.credit and self.debit:
            self.debit = 0

    @api.onchange('debit')
    def _debit_onchange(self):
        if self.debit and self.credit:
            self.credit = 0

    @api.onchange('currency_id', 'amount_currency')
    def _amount_currency_change(self):
        if (
                self.currency_id and
                self.amount_currency and
                not self.credit and
                not self.debit):
            date = self.date or None
            amount_company_currency = self.currency_id.with_context(
                date=date).compute(
                    self.amount_currency, self.env.user.company_id.currency_id)
            precision = self.env['decimal.precision'].precision_get('Account')
            if float_compare(
                    amount_company_currency, 0,
                    precision_digits=precision) == -1:
                self.debit = amount_company_currency * -1
            else:
                self.credit = amount_company_currency


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    # Disable guessing for reconciliation
    # because my experience with several customers shows that it is a problem
    # in the following scenario : move line 'x' has been "guessed" by OpenERP
    # to be reconciled with a statement line 'Y' at the end of the bank
    # statement, but it is a mistake because it should be reconciled with
    # statement line 'B' at the beginning of the bank statement
    # When the user is on statement line 'B', he tries to select
    # move line 'x', but it can't find it... because it is already "reserved"
    # by the guess of OpenERP for statement line 'Y' ! To solve this problem,
    # the user must go to statement line 'Y' and unselect move line 'x'
    # and then come back on statement line 'B' and select move line 'A'...
    # but non super-expert users can't do that because it is impossible to
    # figure out that the fact that the user can't find move line 'x'
    # is caused by this.
    # Set search_reconciliation_proposition to False by default
    def get_data_for_reconciliations(
            self, cr, uid, ids, excluded_ids=None,
            search_reconciliation_proposition=False, context=None):
        # Make variable name shorted for PEP8 !
        search_rec_prop = search_reconciliation_proposition
        return super(AccountBankStatementLine, self).\
            get_data_for_reconciliations(
                cr, uid, ids, excluded_ids=excluded_ids,
                search_reconciliation_proposition=search_rec_prop,
                context=context)

    @api.multi
    def show_account_move(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window'].for_xml_id(
            'account', 'action_move_journal_line')
        if self.journal_entry_id:
            action.update({
                'views': False,
                'view_id': False,
                'view_mode': 'form,tree',
                'res_id': self.journal_entry_id.id,
                })
            return action
        else:
            raise UserError(_(
                'No journal entry linked to this bank statement line.'))

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.multi
    def show_receivable_account(self):
        self.ensure_one()
        account_id = self.property_account_receivable.id
        return self.common_show_account(self.ids[0], account_id)

    @api.multi
    def show_payable_account(self):
        self.ensure_one()
        account_id = self.property_account_payable.id
        return self.common_show_account(self.ids[0], account_id)

    def common_show_account(self, partner_id, account_id):
        action = self.env['ir.actions.act_window'].for_xml_id(
            'account', 'action_account_moves_all_tree')
        action['context'] = {
            'search_default_partner_id': [partner_id],
            'default_partner_id': partner_id,
            'search_default_account_id': account_id,
            }
        return action

    @api.multi
    def _compute_journal_item_count(self):
        amlo = self.env['account.move.line']
        for partner in self:
            partner.journal_item_count = amlo.search_count([
                ('partner_id', '=', partner.id),
                ('account_id', '=', partner.property_account_receivable.id)])
            partner.payable_journal_item_count = amlo.search_count([
                ('partner_id', '=', partner.id),
                ('account_id', '=', partner.property_account_payable.id)])

    journal_item_count = fields.Integer(
        compute='_compute_journal_item_count',
        string="Journal Items", readonly=True)
    payable_journal_item_count = fields.Integer(
        compute='_compute_journal_item_count',
        string="Payable Journal Items", readonly=True)


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    @api.model
    def get_fiscal_position_no_partner(
            self, company_id=None, vat_subjected=False, country_id=None):
        '''This method is inspired by the method get_fiscal_position()
        in odoo/addons/account/partner.py : it uses the same algo
        but without a real partner.
        Returns a recordset of fiscal position, or False'''
        domains = [[
            ('auto_apply', '=', True),
            ('vat_required', '=', vat_subjected),
            ('company_id', '=', company_id)]]
        if vat_subjected:
            domains += [[
                ('auto_apply', '=', True),
                ('vat_required', '=', False),
                ('company_id', '=', company_id)]]

        for domain in domains:
            if country_id:
                fps = self.search(
                    domain + [('country_id', '=', country_id)], limit=1)
                if fps:
                    return fps[0]

                fps = self.search(
                    domain +
                    [('country_group_id.country_ids', '=', country_id)],
                    limit=1)
                if fps:
                    return fps[0]

            fps = self.search(
                domain +
                [('country_id', '=', None), ('country_group_id', '=', None)],
                limit=1)
            if fps:
                return fps[0]
        return False
