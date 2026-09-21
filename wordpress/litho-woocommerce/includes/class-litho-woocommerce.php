<?php

defined('ABSPATH') || exit;

final class Litho_WC_Integration {
    private $api;
    private $settings;

    public function __construct(Litho_WC_API $api, Litho_WC_Settings $settings) {
        $this->api = $api;
        $this->settings = $settings;
    }

    public function register() {
        add_action('wp_enqueue_scripts', array($this, 'enqueue'));
        add_action('woocommerce_before_add_to_cart_button', array($this, 'render_configurator'));
        add_filter('woocommerce_add_to_cart_validation', array($this, 'validate_add_to_cart'), 10, 3);
        add_filter('woocommerce_add_cart_item_data', array($this, 'cart_item_data'), 10, 3);
        add_filter('woocommerce_get_item_data', array($this, 'display_cart_data'), 10, 2);
        add_action('woocommerce_checkout_create_order_line_item', array($this, 'order_line_item'), 10, 4);
        add_action('woocommerce_checkout_order_processed', array($this, 'attach_order'), 10, 3);
        add_action('litho_wc_retry_order_attach', array($this, 'retry_attach_order'));
        add_filter('woocommerce_quantity_input_args', array($this, 'quantity_input_args'), 10, 2);
        add_filter('woocommerce_update_cart_validation', array($this, 'validate_cart_quantity'), 10, 4);
        add_action('woocommerce_after_order_itemmeta', array($this, 'admin_item_actions'), 10, 3);
        add_action('admin_post_litho_download', array($this, 'download'));
    }

    public function enqueue() {
        if (!is_product()) {
            return;
        }
        $product = wc_get_product(get_queried_object_id());
        if (!$product || get_post_meta($product->get_id(), '_litho_enabled', true) !== 'yes') {
            return;
        }
        if (!defined('DONOTCACHEPAGE')) {
            define('DONOTCACHEPAGE', true);
        }
        nocache_headers();
        wp_enqueue_style('litho-configurator', LITHO_WC_URL . 'assets/configurator.css', array(), LITHO_WC_VERSION);
        wp_enqueue_script('litho-configurator', LITHO_WC_URL . 'assets/configurator.js', array(), LITHO_WC_VERSION, true);
        $csrf = WC()->session ? (string) WC()->session->get('litho_csrf') : '';
        if ($csrf === '') {
            $csrf = bin2hex(random_bytes(32));
            if (WC()->session) {
                WC()->session->set('litho_csrf', $csrf);
            }
        }
        wp_localize_script('litho-configurator', 'LithoConfig', array(
            'restUrl' => esc_url_raw(rest_url(Litho_WC_REST::REST_NAMESPACE)),
            'nonce' => wp_create_nonce('litho_configurator'),
            'csrf' => $csrf,
            'productId' => $product->get_id(),
            'housingColors' => $this->settings->housing_colors(),
            'ledColors' => $this->settings->led_colors(),
            'messages' => array(
                'chooseImage' => __('Najpierw wybierz zdjęcie.', 'litho-wc'),
                'working' => __('Przygotowujemy projekt…', 'litho-wc'),
                'ready' => __('Projekt jest gotowy. Możesz dodać produkt do koszyka.', 'litho-wc'),
                'failed' => __('Nie udało się przygotować projektu.', 'litho-wc'),
            ),
        ));
    }

    public function render_configurator() {
        global $product;
        if (!is_a($product, 'WC_Product')) {
            $product = wc_get_product(get_queried_object_id());
        }
        if (!$product || get_post_meta($product->get_id(), '_litho_enabled', true) !== 'yes') {
            return;
        }
        ?>
        <section class="litho-configurator" id="litho-configurator">
            <header><span>L</span><div><strong><?php esc_html_e('Zaprojektuj swoją litofanię', 'litho-wc'); ?></strong><small><?php esc_html_e('Zdjęcie pozostaje prywatne i jest używane wyłącznie do realizacji zamówienia.', 'litho-wc'); ?></small></div></header>
            <div class="litho-grid">
                <div class="litho-controls">
                    <label class="litho-upload"><input type="file" accept="image/jpeg,image/png"><b><?php esc_html_e('Wybierz zdjęcie', 'litho-wc'); ?></b><small>JPG lub PNG · maks. 20 MB</small></label>
                    <div class="litho-field"><label for="litho-size"><?php esc_html_e('Rozmiar', 'litho-wc'); ?></label><select id="litho-size"><option value="100x150">10 × 15 cm</option><option value="130x180">13 × 18 cm</option><option value="150x200">15 × 20 cm</option></select></div>
                    <div class="litho-field"><label><?php esc_html_e('Orientacja', 'litho-wc'); ?></label><div class="litho-segment"><button type="button" data-orientation="landscape" class="active"><?php esc_html_e('Pozioma', 'litho-wc'); ?></button><button type="button" data-orientation="portrait"><?php esc_html_e('Pionowa', 'litho-wc'); ?></button></div></div>
                    <div class="litho-field"><label for="litho-housing-color"><?php esc_html_e('Kolor obudowy', 'litho-wc'); ?></label><select id="litho-housing-color"></select></div>
                    <div class="litho-field"><label for="litho-led-color"><?php esc_html_e('Barwa LED', 'litho-wc'); ?></label><select id="litho-led-color"></select></div>
                    <div class="litho-field"><label><?php esc_html_e('Obrót zdjęcia', 'litho-wc'); ?></label><div class="litho-segment"><button type="button" data-rotate="-90">↶ 90°</button><button type="button" data-rotate="90">90° ↷</button></div></div>
                    <div class="litho-field"><label for="litho-zoom"><?php esc_html_e('Powiększenie', 'litho-wc'); ?></label><input id="litho-zoom" type="range" min="1" max="3" value="1" step="0.01"></div>
                </div>
                <div class="litho-preview-wrap"><canvas id="litho-preview" width="900" height="600"></canvas><p><?php esc_html_e('Przeciągnij zdjęcie, aby ustawić kadr. Kółko myszy zmienia powiększenie.', 'litho-wc'); ?></p></div>
            </div>
            <button class="litho-approve" id="litho-approve" type="button"><?php esc_html_e('Zatwierdź projekt', 'litho-wc'); ?></button>
            <div class="litho-status" id="litho-status" role="status" aria-live="polite"></div>
            <input type="hidden" name="litho_project_id" id="litho-project-id" value="">
            <input type="hidden" name="litho_project_signature" id="litho-project-signature" value="">
        </section>
        <?php
    }

    public function validate_add_to_cart($passed, $product_id, $quantity) {
        if (get_post_meta($product_id, '_litho_enabled', true) !== 'yes') {
            return $passed;
        }
        if ((int) $quantity !== 1) {
            wc_add_notice(__('Każdy projekt Litho jest osobnym produktem. Dodaj go do koszyka w liczbie jednej sztuki.', 'litho-wc'), 'error');
            return false;
        }
        $project_id = sanitize_text_field(wp_unslash($_POST['litho_project_id'] ?? ''));
        $signature = sanitize_text_field(wp_unslash($_POST['litho_project_signature'] ?? ''));
        if (!preg_match('/^LTH-[0-9]{8}-[A-F0-9]{8}$/', $project_id)
            || !WC()->session
            || !hash_equals(Litho_WC_REST::cart_signature($project_id, $product_id, WC()->session->get_customer_id()), $signature)) {
            wc_add_notice(__('Zatwierdź projekt Litho przed dodaniem produktu do koszyka.', 'litho-wc'), 'error');
            return false;
        }
        foreach (WC()->cart->get_cart() as $item) {
            if (($item['litho_project_id'] ?? '') === $project_id) {
                wc_add_notice(__('Ten projekt Litho znajduje się już w koszyku.', 'litho-wc'), 'error');
                return false;
            }
        }
        $project = $this->api->admin_request('GET', '/api/admin/projects/' . rawurlencode($project_id));
        if (is_wp_error($project) || ($project['status'] ?? '') !== 'completed' || !empty($project['customer_ref'])) {
            wc_add_notice(__('Projekt Litho nie jest gotowy albo został już wykorzystany.', 'litho-wc'), 'error');
            return false;
        }
        $config = $project['config'] ?? array();
        if (($config['housing_type'] ?? '') !== (get_post_meta($product_id, '_litho_housing_type', true) ?: 'frame')) {
            wc_add_notice(__('Projekt nie pasuje do wybranego produktu.', 'litho-wc'), 'error');
            return false;
        }
        $GLOBALS['litho_validated_project'] = $project;
        return $passed;
    }

    public function cart_item_data($data, $product_id, $variation_id) {
        if (get_post_meta($product_id, '_litho_enabled', true) !== 'yes') {
            return $data;
        }
        $project = $GLOBALS['litho_validated_project'] ?? null;
        if (!is_array($project)) {
            return $data;
        }
        $data['litho_project_id'] = $project['project_id'];
        $data['litho_config'] = $project['config'];
        $data['litho_unique'] = wp_generate_uuid4();
        unset($GLOBALS['litho_validated_project']);
        return $data;
    }

    public function display_cart_data($display, $cart_item) {
        if (empty($cart_item['litho_project_id']) || empty($cart_item['litho_config'])) {
            return $display;
        }
        foreach ($this->display_values($cart_item['litho_project_id'], $cart_item['litho_config']) as $label => $value) {
            $display[] = array('key' => $label, 'value' => $value);
        }
        return $display;
    }

    public function order_line_item($item, $cart_item_key, $values, $order) {
        if (empty($values['litho_project_id']) || empty($values['litho_config'])) {
            return;
        }
        $item->add_meta_data('_litho_project_id', $values['litho_project_id'], true);
        $item->add_meta_data('_litho_config', wp_json_encode($values['litho_config']), true);
        foreach ($this->display_values($values['litho_project_id'], $values['litho_config']) as $label => $value) {
            $item->add_meta_data($label, $value, true);
        }
    }

    public function attach_order($order_id, $posted_data, $order) {
        $this->attach_projects_to_order($order_id, $order);
    }

    public function retry_attach_order($order_id) {
        $order = wc_get_order($order_id);
        if ($order) {
            $this->attach_projects_to_order($order_id, $order);
        }
    }

    public function quantity_input_args($args, $product) {
        if ($product && get_post_meta($product->get_id(), '_litho_enabled', true) === 'yes') {
            $args['input_value'] = 1;
            $args['min_value'] = 1;
            $args['max_value'] = 1;
        }
        return $args;
    }

    public function validate_cart_quantity($passed, $cart_item_key, $values, $quantity) {
        if (!empty($values['litho_project_id']) && (int) $quantity !== 1) {
            wc_add_notice(__('Każdy projekt Litho musi pozostać osobną pozycją w koszyku.', 'litho-wc'), 'error');
            return false;
        }
        return $passed;
    }

    private function attach_projects_to_order($order_id, $order) {
        $failed = array();
        foreach ($order->get_items() as $item) {
            $project_id = $item->get_meta('_litho_project_id', true);
            if (!$project_id) {
                continue;
            }
            $result = $this->api->admin_request(
                'PUT',
                '/api/admin/projects/' . rawurlencode($project_id) . '/order',
                array('order_id' => 'WC-' . (string) $order_id)
            );
            if (is_wp_error($result)) {
                $failed[] = $project_id;
            }
        }
        if (!$failed) {
            $order->delete_meta_data('_litho_attach_attempts');
            $order->save();
            return;
        }
        $attempt = min(5, (int) $order->get_meta('_litho_attach_attempts', true) + 1);
        $order->update_meta_data('_litho_attach_attempts', $attempt);
        $note = $attempt < 5
            ? sprintf(
                __('Nie udało się przypisać projektu Litho (%1$s). Automatyczna próba %2$d z 5 została zaplanowana.', 'litho-wc'),
                implode(', ', $failed),
                $attempt
            )
            : sprintf(
                __('Nie udało się przypisać projektu Litho (%s) po 5 próbach. Wymagana jest ręczna kontrola połączenia z API.', 'litho-wc'),
                implode(', ', $failed)
            );
        $order->add_order_note($note);
        $order->save();
        if ($attempt < 5 && !wp_next_scheduled('litho_wc_retry_order_attach', array((int) $order_id))) {
            wp_schedule_single_event(time() + min(HOUR_IN_SECONDS, 300 * (2 ** ($attempt - 1))), 'litho_wc_retry_order_attach', array((int) $order_id));
        }
    }

    public function admin_item_actions($item_id, $item, $product) {
        if (!is_admin() || !current_user_can('manage_woocommerce') || !is_a($item, 'WC_Order_Item_Product')) {
            return;
        }
        $project_id = $item->get_meta('_litho_project_id', true);
        if (!$project_id) {
            return;
        }
        $order_id = (int) $item->get_order_id();
        $base_url = admin_url('admin-post.php?action=litho_download&order_id=' . $order_id . '&project_id=' . rawurlencode($project_id));
        $nonce_action = 'litho_download_' . $order_id . '_' . $project_id;
        $source = wp_nonce_url($base_url . '&artifact=source', $nonce_action);
        $stl = wp_nonce_url($base_url . '&artifact=stl', $nonce_action);
        echo '<p class="litho-admin-actions"><a class="button" href="' . esc_url($source) . '">' . esc_html__('Pobierz zdjęcie Litho', 'litho-wc') . '</a> '
            . '<a class="button" href="' . esc_url($stl) . '">' . esc_html__('Pobierz STL Litho', 'litho-wc') . '</a></p>';
    }

    public function download() {
        if (!current_user_can('manage_woocommerce')) {
            wp_die(esc_html__('Brak uprawnień.', 'litho-wc'), '', array('response' => 403));
        }
        $order_id = absint($_GET['order_id'] ?? 0);
        $project_id = sanitize_text_field(wp_unslash($_GET['project_id'] ?? ''));
        $artifact = sanitize_key(wp_unslash($_GET['artifact'] ?? ''));
        check_admin_referer('litho_download_' . $order_id . '_' . $project_id);
        if (!preg_match('/^LTH-[0-9]{8}-[A-F0-9]{8}$/', $project_id) || !in_array($artifact, array('source', 'stl'), true)) {
            wp_die(esc_html__('Nieprawidłowy plik.', 'litho-wc'), '', array('response' => 400));
        }
        $order = wc_get_order($order_id);
        if (!$order || !$this->order_contains_project($order, $project_id)) {
            wp_die(esc_html__('Projekt nie należy do wskazanego zamówienia.', 'litho-wc'), '', array('response' => 403));
        }
        $result = $this->api->download_admin($project_id, $artifact);
        if (is_wp_error($result)) {
            wp_die(esc_html($result->get_error_message()), '', array('response' => 502));
        }
        $source_extension = stripos((string) $result['content_type'], 'png') !== false ? '.png' : '.jpg';
        $filename = $artifact === 'source' ? $project_id . '-source' . $source_extension : $project_id . '-lithophane.stl';
        $file_size = is_file($result['file']) ? filesize($result['file']) : false;
        if ($file_size === false) {
            wp_delete_file($result['file']);
            wp_die(esc_html__('Pobrany plik jest niedostępny.', 'litho-wc'), '', array('response' => 502));
        }
        register_shutdown_function('wp_delete_file', $result['file']);
        nocache_headers();
        header('Content-Type: ' . ($result['content_type'] ?: 'application/octet-stream'));
        header('Content-Disposition: attachment; filename="' . sanitize_file_name($filename) . '"');
        header('Content-Length: ' . $file_size);
        if (function_exists('wc_get_logger')) {
            wc_get_logger()->info(
                sprintf('User %d downloaded %s for project %s from order %d.', get_current_user_id(), $artifact, $project_id, $order_id),
                array('source' => 'litho-wc')
            );
        }
        readfile($result['file']); // phpcs:ignore WordPress.WP.AlternativeFunctions.file_system_operations_readfile
        wp_delete_file($result['file']);
        exit;
    }

    private function order_contains_project($order, $project_id) {
        foreach ($order->get_items() as $item) {
            if (hash_equals((string) $item->get_meta('_litho_project_id', true), (string) $project_id)) {
                return true;
            }
        }
        return false;
    }

    private function display_values($project_id, $config) {
        $housing_colors = $this->settings->housing_colors();
        $led_colors = $this->settings->led_colors();
        return array(
            __('Projekt Litho', 'litho-wc') => $project_id,
            __('Rozmiar Litho', 'litho-wc') => str_replace('x', ' × ', $config['size'] ?? ''),
            __('Orientacja', 'litho-wc') => ($config['orientation'] ?? '') === 'portrait' ? __('Pionowa', 'litho-wc') : __('Pozioma', 'litho-wc'),
            __('Kolor obudowy', 'litho-wc') => $housing_colors[$config['housing_color'] ?? ''] ?? ($config['housing_color'] ?? ''),
            __('Barwa LED', 'litho-wc') => $led_colors[$config['light_temperature'] ?? ''] ?? ($config['light_temperature'] ?? ''),
        );
    }
}
