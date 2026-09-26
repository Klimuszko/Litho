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
        $api_test_code = isset($_GET['litho_api_code']) ? sanitize_key(wp_unslash($_GET['litho_api_code'])) : '';
        $api_test_http = isset($_GET['litho_api_http']) ? absint($_GET['litho_api_http']) : 0;
        ?>
        <div class="wrap">
            <h1><?php esc_html_e('Litho — integracja WooCommerce', 'litho-wc'); ?></h1>
            <?php if ($api_test !== '') : ?>
                <div class="notice <?php echo $api_test === 'success' ? 'notice-success' : 'notice-error'; ?> is-dismissible"><p>
                    <?php echo esc_html($api_test === 'success'
                        ? __('Połączenie z API Litho oraz klucz administratora działają poprawnie.', 'litho-wc')
                        : $this->test_error_message($api_test_code, $api_test_http)); ?>
                </p></div>
            <?php endif; ?>
            <p><?php esc_html_e('Klucz API pozostaje wyłącznie na serwerze WordPress i nigdy nie jest wysyłany do przeglądarki klienta.', 'litho-wc'); ?></p>
            <form method="post" action="options.php">
                <?php settings_fields('litho_wc'); ?>
                <table class="form-table" role="presentation">
                    <tr><th scope="row"><label for="litho_wc_api_url"><?php esc_html_e('Adres API Litho', 'litho-wc'); ?></label></th>
                        <td><input class="regular-text" type="url" id="litho_wc_api_url" name="<?php echo esc_attr(Litho_WC_API::OPTION_URL); ?>" value="<?php echo esc_attr(get_option(Litho_WC_API::OPTION_URL, '')); ?>" placeholder="https://litho.example.pl"></td></tr>
                    <tr><th scope="row"><label for="litho_wc_api_key"><?php esc_html_e('Klucz administratora API', 'litho-wc'); ?></label></th>
                        <td><input class="regular-text" type="password" id="litho_wc_api_key" name="<?php echo esc_attr(Litho_WC_API::OPTION_KEY); ?>" value="" autocomplete="new-password" placeholder="<?php esc_attr_e('Pozostaw puste, aby zachować obecny klucz', 'litho-wc'); ?>" <?php disabled($this->api->uses_config_key()); ?>>
                        <?php if ($this->api->uses_config_key()) : ?><p class="description"><?php esc_html_e('Używany jest klucz LITHO_ADMIN_API_KEY z wp-config.php. Pole w panelu jest ignorowane.', 'litho-wc'); ?></p><?php endif; ?></td></tr>
                    <tr><th scope="row"><label for="litho_wc_housing_colors"><?php esc_html_e('Kolory obudowy', 'litho-wc'); ?></label></th>
                        <td><textarea class="large-text code" rows="5" id="litho_wc_housing_colors" name="<?php echo esc_attr(self::OPTION_HOUSING_COLORS); ?>"><?php echo esc_textarea(get_option(self::OPTION_HOUSING_COLORS, "black-matte|Czarny matowy\nwhite|Biały\nwood|Drewno")); ?></textarea><p class="description">slug|Nazwa, jeden wariant w wierszu</p></td></tr>
                    <tr><th scope="row"><label for="litho_wc_led_colors"><?php esc_html_e('Barwy LED', 'litho-wc'); ?></label></th>
                        <td><textarea class="large-text code" rows="4" id="litho_wc_led_colors" name="<?php echo esc_attr(self::OPTION_LED_COLORS); ?>"><?php echo esc_textarea(get_option(self::OPTION_LED_COLORS, "warm|Ciepła\nneutral|Neutralna\ncool|Zimna")); ?></textarea><p class="description">warm/neutral/cool odpowiadają wartościom API Litho.</p></td></tr>
                </table>
                <?php wp_nonce_field('litho_test_api', 'litho_test_api_nonce'); ?>
                <?php submit_button(); ?>
                <button class="button button-secondary" type="submit" name="action" value="litho_test_api" formmethod="post" formaction="<?php echo esc_url(admin_url('admin-post.php')); ?>"><?php esc_html_e('Testuj i zapisz połączenie', 'litho-wc'); ?></button>
            </form>
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
        check_admin_referer('litho_test_api', 'litho_test_api_nonce');
        $url = $this->sanitize_url(wp_unslash($_POST[Litho_WC_API::OPTION_URL] ?? ''));
        $submitted_key = trim((string) wp_unslash($_POST[Litho_WC_API::OPTION_KEY] ?? ''));
        $key = $submitted_key !== '' ? $submitted_key : (string) get_option(Litho_WC_API::OPTION_KEY, '');
        $result = $this->api->test_connection($url, $key);
        $status = is_wp_error($result) ? 'failure' : 'success';
        if (!is_wp_error($result)) {
            update_option(Litho_WC_API::OPTION_URL, $url);
            if (!$this->api->uses_config_key() && $submitted_key !== '') {
                update_option(Litho_WC_API::OPTION_KEY, $submitted_key);
            }
        }
        $args = array('page' => 'litho-settings', 'litho_api_test' => $status);
        if (is_wp_error($result)) {
            $args['litho_api_code'] = $result->get_error_code();
            $data = $result->get_error_data();
            if (is_array($data) && isset($data['status'])) {
                $args['litho_api_http'] = absint($data['status']);
            }
        }
        wp_safe_redirect(add_query_arg($args, admin_url('admin.php')));
        exit;
    }

    private function test_error_message($code, $http_status) {
        if ($code === 'litho_not_configured') {
            return __('Test nie został wykonany: wpisz poprawny adres API i klucz.', 'litho-wc');
        }
        if ($code === 'litho_api_unavailable') {
            return __('WordPress nie może połączyć się z serwerem Litho. Sprawdź DNS, certyfikat TLS, zaporę i dostęp serwera WordPress do tego adresu.', 'litho-wc');
        }
        if (in_array($http_status, array(301, 302, 307, 308), true)) {
            return sprintf(__('API zwróciło przekierowanie HTTP %d. Wpisz docelowy adres HTTPS bez przekierowania.', 'litho-wc'), $http_status);
        }
        if (in_array($http_status, array(401, 403), true)) {
            return sprintf(__('Serwer Litho odrzucił klucz (HTTP %d). Klucz musi być identyczny z LITHO_ADMIN_API_KEY w kontenerze Litho.', 'litho-wc'), $http_status);
        }
        if ($http_status === 404) {
            return __('Nie znaleziono endpointu Litho (HTTP 404). Podaj główny adres aplikacji, bez dopisywania /api.', 'litho-wc');
        }
        if ($http_status === 503) {
            return __('API Litho nie ma skonfigurowanego LITHO_ADMIN_API_KEY albo usługa jest chwilowo niedostępna (HTTP 503).', 'litho-wc');
        }
        if ($http_status > 0) {
            return sprintf(__('Test API nie powiódł się (HTTP %d).', 'litho-wc'), $http_status);
        }
        return __('Test API nie powiódł się. Sprawdź adres API, klucz administratora oraz dostępność serwera Litho.', 'litho-wc');
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
