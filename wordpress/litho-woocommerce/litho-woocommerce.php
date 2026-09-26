<?php
/**
 * Plugin Name: Litho for WooCommerce
 * Description: Bezpieczny konfigurator litofanii połączony z prywatnym API Litho.
 * Version: 0.1.7
 * Author: Litho
 * Requires at least: 6.4
 * Requires PHP: 7.4
 * WC requires at least: 8.0
 */

defined('ABSPATH') || exit;

define('LITHO_WC_VERSION', '0.1.7');
define('LITHO_WC_FILE', __FILE__);
define('LITHO_WC_DIR', plugin_dir_path(__FILE__));
define('LITHO_WC_URL', plugin_dir_url(__FILE__));

add_action('before_woocommerce_init', static function () {
    if (class_exists(\Automattic\WooCommerce\Utilities\FeaturesUtil::class)) {
        \Automattic\WooCommerce\Utilities\FeaturesUtil::declare_compatibility('custom_order_tables', __FILE__, true);
    }
});

require_once LITHO_WC_DIR . 'includes/class-litho-api.php';
require_once LITHO_WC_DIR . 'includes/class-litho-settings.php';
require_once LITHO_WC_DIR . 'includes/class-litho-rest.php';
require_once LITHO_WC_DIR . 'includes/class-litho-woocommerce.php';

function litho_wc_bootstrap() {
    if (!class_exists('WooCommerce')) {
        add_action('admin_notices', static function () {
            echo '<div class="notice notice-error"><p>'
                . esc_html__('Litho for WooCommerce wymaga aktywnego WooCommerce.', 'litho-wc')
                . '</p></div>';
        });
        return;
    }

    $api = new Litho_WC_API();
    $settings = new Litho_WC_Settings($api);
    $rest = new Litho_WC_REST($api, $settings);
    $woocommerce = new Litho_WC_Integration($api, $settings);

    $settings->register();
    $rest->register();
    $woocommerce->register();
}
add_action('plugins_loaded', 'litho_wc_bootstrap');
