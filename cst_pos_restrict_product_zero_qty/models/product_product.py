# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config_id):
        data = super()._load_pos_data_fields(config_id)
        data += ['qty_available', ]
        return data

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        location = config.picking_type_id.default_location_src_id
        if location:
            qty_by_product = {}
            for tmpl in records:
                variant_qty = sum(
                    tmpl.product_variant_ids.with_context(location=location.id).mapped('qty_available')
                )
                qty_by_product[tmpl.id] = variant_qty
            for product in read_records:
                if product['id'] in qty_by_product:
                    product['qty_available'] = qty_by_product[product['id']]
        return read_records


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        data = super()._load_pos_data_fields(config_id)
        data += ['qty_available', ]
        return data

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        location = config.picking_type_id.default_location_src_id
        if location:
            records_at_location = records.with_context(location=location.id)
            qty_by_product = dict(zip(records_at_location.ids, records_at_location.mapped('qty_available')))
            for product in read_records:
                if product['id'] in qty_by_product:
                    product['qty_available'] = qty_by_product[product['id']]
        return read_records
