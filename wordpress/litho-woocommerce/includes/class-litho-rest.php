<?php

defined('ABSPATH') || exit;

final class Litho_WC_REST {
    const REST_NAMESPACE = 'litho/v1';
    const TRANSIENT_PREFIX = 'litho_wc_project_';

    private $api;
    private $settings;

    public function __construct(Litho_WC_API $api, Litho_WC_Settings $settings) {
        $this->api = $api;
        $this->settings = $settings;
    }

    public function register() {
        add_action('rest_api_init', array($this, 'routes'));
    }

    public function routes() {
        register_rest_route(self::REST_NAMESPACE, '/projects', array(
            'methods' => 'POST',
            'callback' => array($this, 'create_project'),
            'permission_callback' => array($this, 'permission'),
        ));
        register_rest_route(self::REST_NAMESPACE, '/projects/(?P<project_id>LTH-[0-9]{8}-[A-F0-9]{8})/image', array(
            'methods' => 'POST',
            'callback' => array($this, 'upload_image'),
            'permission_callback' => array($this, 'permission'),
        ));
        register_rest_route(self::REST_NAMESPACE, '/projects/(?P<project_id>LTH-[0-9]{8}-[A-F0-9]{8})/generate', array(
            'methods' => 'POST',
            'callback' => array($this, 'generate'),
            'permission_callback' => array($this, 'permission'),
        ));
        register_rest_route(self::REST_NAMESPACE, '/projects/(?P<project_id>LTH-[0-9]{8}-[A-F0-9]{8})', array(
            'methods' => 'GET',
            'callback' => array($this, 'status'),
            'permission_callback' => array($this, 'permission'),
        ));
    }

    public function permission(WP_REST_Request $request) {
        $nonce = (string) $request->get_header('X-Litho-Nonce');
        if ($nonce === '' || !wp_verify_nonce($nonce, 'litho_configurator')) {
            return new WP_Error('litho_invalid_nonce', __('Sesja konfiguratora wygasła. Odśwież stronę.', 'litho-wc'), array('status' => 403));
        }
        $expected = WC()->session ? (string) WC()->session->get('litho_csrf') : '';
        $received = (string) $request->get_header('X-Litho-CSRF-Token');
        if ($expected === '' || $received === '' || !hash_equals($expected, $received)) {
            return new WP_Error('litho_invalid_session', __('Sesja konfiguratora wygasła. Odśwież stronę.', 'litho-wc'), array('status' => 403));
        }
        $origin = (string) ($request->get_header('Origin') ?: $request->get_header('Referer'));
        if ($origin !== '' && wp_parse_url($origin, PHP_URL_HOST) !== wp_parse_url(home_url('/'), PHP_URL_HOST)) {
            return new WP_Error('litho_invalid_origin', __('Nieprawidłowe źródło żądania.', 'litho-wc'), array('status' => 403));
        }
        return true;
    }

    public function create_project(WP_REST_Request $request) {
        if (!$this->allow_create()) {
            return new WP_Error('litho_rate_limit', __('Zbyt wiele nowych projektów. Spróbuj ponownie później.', 'litho-wc'), array('status' => 429));
        }
        $product_id = absint($request->get_param('product_id'));
        $product = wc_get_product($product_id);
        if (!$product || get_post_meta($product_id, '_litho_enabled', true) !== 'yes' || $product->get_status() !== 'publish') {
            return new WP_Error('litho_product_invalid', __('Ten produkt nie obsługuje konfiguratora Litho.', 'litho-wc'), array('status' => 400));
        }
        $config = $this->validated_config($request, $product_id);
        if (is_wp_error($config)) {
            return $config;
        }
        $created = $this->api->customer_request('POST', '/api/customer/projects', $config);
        if (is_wp_error($created)) {
            return $created;
        }
        if (empty($created['project_id']) || empty($created['project_token'])) {
            return new WP_Error('litho_api_contract', __('API Litho zwróciło niepełną odpowiedź.', 'litho-wc'), array('status' => 502));
        }
        $browser_token = wp_generate_password(48, false, false);
        $encrypted_token = $this->encrypt_token($created['project_token']);
        if (is_wp_error($encrypted_token)) {
            return $encrypted_token;
        }
        $session_id = WC()->session ? (string) WC()->session->get_customer_id() : '';
        $record = array(
            'project_id' => $created['project_id'],
            'project_token_encrypted' => $encrypted_token,
            'browser_token_hash' => hash('sha256', $browser_token),
            'session_id' => $session_id,
            'product_id' => $product_id,
            'config' => $config,
            'created_at' => time(),
        );
        set_transient($this->transient_key($created['project_id']), $record, DAY_IN_SECONDS);
        return rest_ensure_response(array(
            'project_id' => $created['project_id'],
            'browser_token' => $browser_token,
            'cart_signature' => self::cart_signature($created['project_id'], $product_id, $session_id),
            'status' => $created['status'] ?? 'awaiting_image',
        ));
    }

    public function upload_image(WP_REST_Request $request) {
        $record = $this->authorized_record($request);
        if (is_wp_error($record)) {
            return $record;
        }
        if (!empty($record['image_uploaded_at'])) {
            return new WP_Error('litho_image_already_uploaded', __('Zdjęcie dla tego projektu zostało już przesłane.', 'litho-wc'), array('status' => 409));
        }
        $files = $request->get_file_params();
        $file = $files['image'] ?? null;
        if (!$file || ($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
            return new WP_Error('litho_image_required', __('Wybierz poprawne zdjęcie.', 'litho-wc'), array('status' => 400));
        }
        if ((int) $file['size'] > 20 * MB_IN_BYTES) {
            return new WP_Error('litho_image_too_large', __('Zdjęcie może mieć maksymalnie 20 MB.', 'litho-wc'), array('status' => 413));
        }
        $mime = wp_get_image_mime($file['tmp_name']);
        if (!in_array($mime, array('image/jpeg', 'image/png'), true)) {
            return new WP_Error('litho_image_type', __('Obsługiwane są wyłącznie pliki JPG i PNG.', 'litho-wc'), array('status' => 415));
        }
        $token = $this->decrypt_token($record['project_token_encrypted']);
        if (is_wp_error($token)) {
            return $token;
        }
        $result = $this->api->upload_image($record['project_id'], $token, $file);
        if (is_wp_error($result)) {
            return $result;
        }
        $record['image_uploaded_at'] = time();
        set_transient($this->transient_key($record['project_id']), $record, DAY_IN_SECONDS);
        return rest_ensure_response(array('status' => $result['status'] ?? 'ready'));
    }

    public function generate(WP_REST_Request $request) {
        $record = $this->authorized_record($request);
        if (is_wp_error($record)) {
            return $record;
        }
        if (!empty($record['generation_started_at'])) {
            return new WP_Error('litho_generation_already_started', __('Generowanie tego projektu zostało już uruchomione.', 'litho-wc'), array('status' => 409));
        }
        $token = $this->decrypt_token($record['project_token_encrypted']);
        if (is_wp_error($token)) {
            return $token;
        }
        $record['generation_started_at'] = time();
        set_transient($this->transient_key($record['project_id']), $record, DAY_IN_SECONDS);
        $result = $this->api->customer_request(
            'POST',
            '/api/customer/projects/' . rawurlencode($record['project_id']) . '/generate',
            null,
            $token
        );
        if (is_wp_error($result)) {
            unset($record['generation_started_at']);
            set_transient($this->transient_key($record['project_id']), $record, DAY_IN_SECONDS);
            return $result;
        }
        return rest_ensure_response(array('status' => $result['status'] ?? 'generating'));
    }

    public function status(WP_REST_Request $request) {
        $record = $this->authorized_record($request);
        if (is_wp_error($record)) {
            return $record;
        }
        $token = $this->decrypt_token($record['project_token_encrypted']);
        if (is_wp_error($token)) {
            return $token;
        }
        $result = $this->api->customer_request(
            'GET',
            '/api/customer/projects/' . rawurlencode($record['project_id']),
            null,
            $token
        );
        if (is_wp_error($result)) {
            return $result;
        }
        return rest_ensure_response(array(
            'project_id' => $record['project_id'],
            'status' => $result['status'] ?? 'failed',
            'generation_error' => $result['generation_error'] ?? null,
        ));
    }

    private function validated_config(WP_REST_Request $request, $product_id) {
        $size = sanitize_text_field((string) $request->get_param('size'));
        $orientation = sanitize_key((string) $request->get_param('orientation'));
        $housing_color = sanitize_title((string) $request->get_param('housing_color'));
        $led = sanitize_title((string) $request->get_param('light_temperature'));
        $housing = get_post_meta($product_id, '_litho_housing_type', true) ?: 'frame';
        $power = get_post_meta($product_id, '_litho_power_source', true) ?: 'wired';
        if (!in_array($size, array('100x150', '130x180', '150x200'), true)
            || !in_array($orientation, array('landscape', 'portrait'), true)
            || !isset($this->settings->housing_colors()[$housing_color])
            || !isset($this->settings->led_colors()[$led])
            || !in_array($led, array('warm', 'neutral', 'cool'), true)
            || !in_array($housing, array('frame', 'box'), true)
            || !in_array($power, array('wired', 'battery'), true)) {
            return new WP_Error('litho_config_invalid', __('Wybrana konfiguracja jest nieprawidłowa.', 'litho-wc'), array('status' => 400));
        }
        $crop = $request->get_param('crop');
        $crop = is_array($crop) ? $crop : array();
        $normalized = array();
        foreach (array('x', 'y', 'width', 'height') as $key) {
            if (!isset($crop[$key]) || !is_numeric($crop[$key])) {
                return new WP_Error('litho_crop_invalid', __('Nieprawidłowe kadrowanie zdjęcia.', 'litho-wc'), array('status' => 400));
            }
            $normalized[$key] = (float) $crop[$key];
        }
        if ($normalized['x'] < 0 || $normalized['y'] < 0 || $normalized['width'] <= 0 || $normalized['height'] <= 0
            || $normalized['x'] + $normalized['width'] > 1.000001 || $normalized['y'] + $normalized['height'] > 1.000001) {
            return new WP_Error('litho_crop_invalid', __('Kadrowanie musi pozostać wewnątrz zdjęcia.', 'litho-wc'), array('status' => 400));
        }
        $normalized['width'] = min($normalized['width'], 1.0 - $normalized['x']);
        $normalized['height'] = min($normalized['height'], 1.0 - $normalized['y']);
        $rotation = (float) $request->get_param('rotation_degrees');
        if (!in_array($rotation, array(-270.0, -180.0, -90.0, 0.0, 90.0, 180.0, 270.0), true)) {
            return new WP_Error('litho_rotation_invalid', __('Nieprawidłowy obrót zdjęcia.', 'litho-wc'), array('status' => 400));
        }
        return array(
            'size' => $size,
            'orientation' => $orientation,
            'housing_type' => $housing,
            'housing_color' => $housing_color,
            'power_source' => $power,
            'light_temperature' => $led,
            'crop' => $normalized,
            'rotation_degrees' => $rotation,
            'brightness' => 1,
            'contrast' => 1.25,
            'gamma' => 1,
        );
    }

    private function authorized_record(WP_REST_Request $request) {
        $project_id = sanitize_text_field((string) $request['project_id']);
        $browser_token = (string) $request->get_header('X-Litho-Project-Key');
        $record = get_transient($this->transient_key($project_id));
        $session_id = WC()->session ? (string) WC()->session->get_customer_id() : '';
        if (!is_array($record) || $browser_token === ''
            || !hash_equals((string) ($record['browser_token_hash'] ?? ''), hash('sha256', $browser_token))
            || empty($record['session_id']) || !hash_equals((string) $record['session_id'], $session_id)) {
            return new WP_Error('litho_project_forbidden', __('Brak dostępu do tego projektu.', 'litho-wc'), array('status' => 403));
        }
        return $record;
    }

    private function allow_create() {
        $session_id = WC()->session ? (string) WC()->session->get_customer_id() : '';
        $address = sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'] ?? 'unknown'));
        $limits = array(
            array('identity' => 'session|' . ($session_id !== '' ? $session_id : $address), 'limit' => 10),
            array('identity' => 'address|' . $address, 'limit' => 100),
        );
        $resolved = array();
        foreach ($limits as $limit) {
            $limit['key'] = 'litho_wc_rate_' . substr(hash('sha256', $limit['identity']), 0, 24);
            if ((int) get_transient($limit['key']) >= $limit['limit']) {
                return false;
            }
            $resolved[] = $limit;
        }
        foreach ($resolved as $limit) {
            set_transient($limit['key'], (int) get_transient($limit['key']) + 1, HOUR_IN_SECONDS);
        }
        return true;
    }

    private function transient_key($project_id) {
        return self::TRANSIENT_PREFIX . strtolower(str_replace('-', '_', $project_id));
    }

    public static function cart_signature($project_id, $product_id, $session_id) {
        return hash_hmac('sha256', $project_id . '|' . absint($product_id) . '|' . $session_id, wp_salt('auth'));
    }

    private function encrypt_token($token) {
        if (!function_exists('openssl_encrypt')) {
            return new WP_Error('litho_crypto_missing', __('Serwer WordPress nie obsługuje wymaganego szyfrowania.', 'litho-wc'), array('status' => 500));
        }
        $key = hash('sha256', wp_salt('auth') . '|litho-wc-project-token', true);
        $iv = random_bytes(12);
        $tag = '';
        $ciphertext = openssl_encrypt($token, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
        if ($ciphertext === false) {
            return new WP_Error('litho_crypto_failed', __('Nie można zabezpieczyć sesji projektu.', 'litho-wc'), array('status' => 500));
        }
        return base64_encode($iv . $tag . $ciphertext);
    }

    private function decrypt_token($payload) {
        $decoded = base64_decode((string) $payload, true);
        if ($decoded === false || strlen($decoded) < 29) {
            return new WP_Error('litho_session_corrupt', __('Sesja projektu jest uszkodzona. Utwórz projekt ponownie.', 'litho-wc'), array('status' => 500));
        }
        $key = hash('sha256', wp_salt('auth') . '|litho-wc-project-token', true);
        $token = openssl_decrypt(substr($decoded, 28), 'aes-256-gcm', $key, OPENSSL_RAW_DATA, substr($decoded, 0, 12), substr($decoded, 12, 16));
        return $token === false
            ? new WP_Error('litho_session_corrupt', __('Sesja projektu jest uszkodzona. Utwórz projekt ponownie.', 'litho-wc'), array('status' => 500))
            : $token;
    }
}
