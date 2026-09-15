/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ProductConfiguratorPopup } from "@point_of_sale/app/components/popups/product_configurator_popup/product_configurator_popup"
import { ComboConfiguratorPopup } from "@point_of_sale/app/components/popups/combo_configurator_popup/combo_configurator_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";


function showOutOfStockDialog(env, product) {
    const msg = _t("%(product)s is out of stock (0 available).", {
        product: product.display_name,
    });

    env.services.dialog.add(AlertDialog, {
        title: _t("Quantity Restriction"),
        body: msg,
    });
}

function isOutOfStock(pos, product) {
    return (
        pos.config.prod_zero_qty_restrict &&
        product?.type === "consu" &&
        product?.is_storable &&
        product?.qty_available <= 0
    );
}

patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        if (isOutOfStock(this.env.services.pos, product)) {
            showOutOfStockDialog(this.env, product);
            return;
        }
        return super.addProductToOrder(product);
    },
});

patch(ProductConfiguratorPopup.prototype, {
    async confirm() {
        const pos = this.env.services.pos;
        const product = this?.product;

        if (isOutOfStock(pos, product)) {
            showOutOfStockDialog(this.env, product);
            return;
        }
        return super.confirm();
    },
});

patch(ComboConfiguratorPopup.prototype, {
    isProductOutOfStock(comboItem) {
        const product = comboItem.product_id;
        return isOutOfStock(this.pos, product);
    },

    async confirm() {
        // Returns two array[changes in Odoo19]
        const [itemsIncluded, itemsExtra] = this.getSelectedComboItems();
        const allSelectedItems = [...itemsIncluded, ...itemsExtra];

        const outItem = allSelectedItems.find((item) =>
            this.isProductOutOfStock(item.combo_item_id)
        );

        if (outItem) {
            showOutOfStockDialog(this.env, outItem.combo_item_id.product_id);
            return;
        }

        return super.confirm();
    },
});
