<?php

defined('ABSPATH') || exit;

final class Litho_WC_Settings {
    const OPTION_HOUSING_COLORS = 'litho_wc_housing_colors';
    const OPTION_LED_COLORS = 'litho_wc_led_colors';

    private $api;

    public function __construct(Litho_WC_API $api) {
        $this->api = $api;
    }

    public function register() {
        add_action('admin_menu', array($this, 'admin_menu'));
        add_action('admin_init', array($this, 'register_settings'));
        add_filter('option_page_capability_litho_wc', array($this, 'settings_capability'));
        add_action('admin_post_litho_test_api', array($this, 'test_api'));
        add_action('woocommerce_product_options_general_product_data', array($this, 'product_fields'));
        add_action('woocommerce_process_product_meta', array($this, 'save_product_fields'));
    }

    public function settings_capability() {
        return 'manage_options';
    }

    public function admin_menu() {
        add_submenu_page(
            'woocommerce',
            __('Litho', 'litho-wc'),
            __('Litho', 'litho-wc'),
            'manage_options',
            'litho-settings',
            array($this, 'render_page')
        );
    }

    public function register_settings() {
        register_setting('litho_wc', Litho_WC_API::OPTION_URL, array('sanitize_callback' => array($this, 'sanitize_url')));
        register_setting('litho_wc', Litho_WC_API::OPTION_KEY, array('sanitize_callback' => array($this, 'sanitize_key')));
        register_setting('litho_wc', self::OPTION_HOUSING_COLORS, array('sanitize_callback' => array($this, 'sanitize_choices')));
        register_setting('litho_wc', self::OPTION_LED_COLORS, array('sanitize_callback' => array($this, 'sanitize_choices')));
    }

    public function sanitize_url($value) {
        $url = untrailingslashit(esc_url_raw(trim((string) $value), array('http', 'https')));
        return wp_http_validate_url($url) ? $url : '';
    }

    public function sanitize_key($value) {
        $value = trim((string) $value);
        return $value === '' ? (string) get_option(Litho_WC_API::OPTION_KEY, '') : $value;
    }

    public function sanitize_choices($value) {
        $valid = array();
        foreach (preg_split('/\r\n|\r|\n/', (string) $value) as $line) {
            $parts = array_map('trim', explode('|', $line, 2));
            $slug = sanitize_title($parts[0] ?? '');
            $label = sanitize_text_field($parts[1] ?? '');
            if ($slug !== '' && $label !== '') {
                $valid[$slug] = $label;
            }
        }
        return implode("\n", array_map(static function ($slug, $label) {
            return $slug . '|' . $label;
        }, array_keys($valid), $valid));
    }

    public function render_page() {
        if (!current_user_can('manage_options')) {
            return;
        }
        $api_test = isset($_GET['litho_api_test'])
            ? sanitize_key(wp_unslash($_GET['litho_api_test']))
            : '';
        ?>
        <div class="wrap">
            <h1><?php esc_html_e('Litho — integracja WooCommerce', 'litho-wc'); ?></h1>
            <?php if ($api_test !== '') : ?>
                <div class="notice <?php echo $api_test === 'success' ? 'notice-success' : 'notice-error'; ?> is-dismissible"><p>
                    <?php echo $api_test === 'success'
                        ? esc_html__('Połączenie z API Litho oraz klucz administratora działają poprawnie.', 'litho-wc')
                        : esc_html__('Test API nie powiódł się. Sprawdź adres API, klucz administratora oraz dostępność serwera Litho.', 'litho-wc'); ?>
                </p></div>
            <?php endif; ?>
            <p><?php esc_html_e('Klucz API pozostaje wyłącznie na serwerze WordPress i nigdy nie jest wysyłany do przeglądarki klienta.', 'litho-wc'); ?></p>
            <form method="post" action="options.php">
                <?php settings_fields('litho_wc'); ?>
                <table class="form-table" role="presentation">
                    <tr><th scope="row"><label for="litho_wc_api_url"><?php esc_html_e('Adres API Litho', 'litho-wc'); ?></label></th>
                        <td><input class="regular-text" type="url" id="litho_wc_api_url" name="<?php echo esc_attr(Litho_WC_API::OPTION_URL); ?>" value="<?php echo esc_attr(get_option(Litho_WC_API::OPTION_URL, '')); ?>" placeholder="https://litho.example.pl"></td></tr>
                    <tr><th scope="row"><label for="litho_wc_api_key"><?php esc_html_e('Klucz administratora API', 'litho-wc'); ?></label></th>
                        <td><input class="regular-text" type="password" id="litho_wc_api_key" name="<?php echo esc_attr(Litho_WC_API::OPTION_KEY); ?>" value="" autocomplete="new-password" placeholder="<?php esc_attr_e('Pozostaw puste, aby zachować obecny klucz', 'litho-wc'); ?>"></td></tr>
                    <tr><th scope="row"><label for="litho_wc_housing_colors"><?php esc_html_e('Kolory obudowy', 'litho-wc'); ?></label></th>
                        <td><textarea class="large-text code" rows="5" id="litho_wc_housing_colors" name="<?php echo esc_attr(self::OPTION_HOUSING_COLORS); ?>"><?php echo esc_textarea(get_option(self::OPTION_HOUSING_COLORS, "black-matte|Czarny matowy\nwhite|Biały\nwood|Drewno")); ?></textarea><p class="description">slug|Nazwa, jeden wariant w wierszu</p></td></tr>
                    <tr><th scope="row"><label for="litho_wc_led_colors"><?php esc_html_e('Barwy LED', 'litho-wc'); ?></label></th>
                        <td><textarea class="large-text code" rows="4" id="litho_wc_led_colors" name="<?php echo esc_attr(self::OPTION_LED_COLORS); ?>"><?php echo esc_textarea(get_option(self::OPTION_LED_COLORS, "warm|Ciepła\nneutral|Neutralna\ncool|Zimna")); ?></textarea><p class="description">warm/neutral/cool odpowiadają wartościom API Litho.</p></td></tr>
                </table>
                <?php submit_button(); ?>
            </form>
            <p><a class="button button-secondary" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=litho_test_api'), 'litho_test_api')); ?>"><?php esc_html_e('Testuj połączenie z API', 'litho-wc'); ?></a></p>
        </div>
        <?php
    }

    public function product_fields() {
        echo '<div class="options_group">';
        woocommerce_wp_checkbox(array(
            'id' => '_litho_enabled',
            'label' => __('Konfigurator Litho', 'litho-wc'),
            'description' => __('Włącz konfigurator zdjęcia na stronie tego produktu.', 'litho-wc'),
        ));
        woocommerce_wp_select(array(
            'id' => '_litho_housing_type',
            'label' => __('Typ produktu Litho', 'litho-wc'),
            'options' => array('frame' => __('Ramka', 'litho-wc'), 'box' => __('Box', 'litho-wc')),
        ));
        echo '</div>';
    }

    public function save_product_fields($product_id) {
        update_post_meta($product_id, '_litho_enabled', isset($_POST['_litho_enabled']) ? 'yes' : 'no');
        $housing = sanitize_key(wp_unslash($_POST['_litho_housing_type'] ?? 'frame'));
        update_post_meta($product_id, '_litho_housing_type', in_array($housing, array('frame', 'box'), true) ? $housing : 'frame');
        delete_post_meta($product_id, '_litho_power_source');
    }

    public function test_api() {
        if (!current_user_can('manage_options')) {
            wp_die(esc_html__('Brak uprawnień.', 'litho-wc'), '', array('response' => 403));
        }
        check_admin_referer('litho_test_api');
        $result = $this->api->admin_request('GET', '/api/admin/projects');
        $status = is_wp_error($result) ? 'failure' : 'success';
        wp_safe_redirect(add_query_arg(array('page' => 'litho-settings', 'litho_api_test' => $status), admin_url('admin.php')));
        exit;
    }

    public function choices($option, $defaults) {
        $lines = preg_split('/\r\n|\r|\n/', (string) get_option($option, $defaults));
        $choices = array();
        foreach ($lines as $line) {
            $parts = array_map('trim', explode('|', $line, 2));
            if (!empty($parts[0]) && !empty($parts[1])) {
                $choices[sanitize_title($parts[0])] = sanitize_text_field($parts[1]);
            }
        }
        return $choices;
    }

    public function housing_colors() {
        return $this->choices(self::OPTION_HOUSING_COLORS, "black-matte|Czarny matowy\nwhite|Biały\nwood|Drewno");
    }

    public function led_colors() {
        return $this->choices(self::OPTION_LED_COLORS, "warm|Ciepła\nneutral|Neutralna\ncool|Zimna");
    }
}
