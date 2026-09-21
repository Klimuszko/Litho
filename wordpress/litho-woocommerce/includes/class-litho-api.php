<?php

defined('ABSPATH') || exit;

final class Litho_WC_API {
    const OPTION_URL = 'litho_wc_api_url';
    const OPTION_KEY = 'litho_wc_api_key';

    public function configured() {
        return $this->base_url() !== '' && $this->api_key() !== '';
    }

    public function base_url() {
        return untrailingslashit((string) get_option(self::OPTION_URL, ''));
    }

    private function api_key() {
        if (defined('LITHO_ADMIN_API_KEY') && LITHO_ADMIN_API_KEY !== '') {
            return (string) LITHO_ADMIN_API_KEY;
        }
        return (string) get_option(self::OPTION_KEY, '');
    }

    public function customer_request($method, $path, $body = null, $project_token = '') {
        $headers = array(
            'Accept' => 'application/json',
            'X-Litho-Admin-Key' => $this->api_key(),
        );
        if ($project_token !== '') {
            $headers['X-Project-Token'] = $project_token;
        }
        return $this->request($method, $path, $body, $headers);
    }

    public function admin_request($method, $path, $body = null) {
        return $this->request($method, $path, $body, array(
            'Accept' => 'application/json',
            'X-Litho-Admin-Key' => $this->api_key(),
        ));
    }

    public function upload_image($project_id, $project_token, $file) {
        $boundary = '----Litho' . wp_generate_password(24, false, false);
        $filename = sanitize_file_name($file['name']);
        $mime = wp_get_image_mime($file['tmp_name']);
        $bytes = file_get_contents($file['tmp_name']);
        if ($bytes === false) {
            return new WP_Error('litho_upload_read', __('Nie można odczytać przesłanego zdjęcia.', 'litho-wc'));
        }
        $payload = '--' . $boundary . "\r\n"
            . 'Content-Disposition: form-data; name="image"; filename="' . str_replace('"', '', $filename) . '"' . "\r\n"
            . 'Content-Type: ' . $mime . "\r\n\r\n"
            . $bytes . "\r\n--" . $boundary . "--\r\n";

        return $this->request('POST', '/api/customer/projects/' . rawurlencode($project_id) . '/image', $payload, array(
            'Accept' => 'application/json',
            'Content-Type' => 'multipart/form-data; boundary=' . $boundary,
            'X-Litho-Admin-Key' => $this->api_key(),
            'X-Project-Token' => $project_token,
        ));
    }

    public function download_admin($project_id, $artifact) {
        $path = $artifact === 'source'
            ? '/api/admin/projects/' . rawurlencode($project_id) . '/source'
            : '/api/admin/projects/' . rawurlencode($project_id) . '/artifacts/lithophane_stl';
        if (!$this->configured()) {
            return new WP_Error('litho_not_configured', __('Połączenie z API Litho nie jest skonfigurowane.', 'litho-wc'));
        }
        $temporary = wp_tempnam($project_id . '-' . $artifact);
        if (!$temporary) {
            return new WP_Error('litho_download_temp', __('Nie można utworzyć pliku tymczasowego.', 'litho-wc'));
        }
        $response = wp_remote_get($this->base_url() . '/' . ltrim($path, '/'), array(
            'timeout' => 300,
            'redirection' => 0,
            'headers' => array('X-Litho-Admin-Key' => $this->api_key()),
            'stream' => true,
            'filename' => $temporary,
        ));
        if (is_wp_error($response)) {
            wp_delete_file($temporary);
            return new WP_Error('litho_api_unavailable', __('API Litho jest chwilowo niedostępne.', 'litho-wc'));
        }
        $status = (int) wp_remote_retrieve_response_code($response);
        if ($status < 200 || $status >= 300) {
            wp_delete_file($temporary);
            return new WP_Error('litho_api_error', __('Pobranie pliku z API Litho nie powiodło się.', 'litho-wc'), array('status' => $status));
        }
        return array(
            'file' => $temporary,
            'content_type' => wp_remote_retrieve_header($response, 'content-type'),
            'content_disposition' => wp_remote_retrieve_header($response, 'content-disposition'),
        );
    }

    private function request($method, $path, $body, $headers) {
        if (!$this->configured()) {
            return new WP_Error('litho_not_configured', __('Połączenie z API Litho nie jest skonfigurowane.', 'litho-wc'));
        }
        $args = array(
            'method' => strtoupper($method),
            'timeout' => 30,
            'redirection' => 0,
            'headers' => $headers,
        );
        if ($body !== null) {
            if (is_array($body)) {
                $args['headers']['Content-Type'] = 'application/json';
                $args['body'] = wp_json_encode($body);
            } else {
                $args['body'] = $body;
            }
        }
        $response = wp_remote_request($this->base_url() . '/' . ltrim($path, '/'), $args);
        if (is_wp_error($response)) {
            return new WP_Error('litho_api_unavailable', __('API Litho jest chwilowo niedostępne.', 'litho-wc'));
        }
        $status = (int) wp_remote_retrieve_response_code($response);
        $response_body = wp_remote_retrieve_body($response);
        if ($status < 200 || $status >= 300) {
            if (function_exists('wc_get_logger')) {
                wc_get_logger()->error('Litho API HTTP ' . $status . ': ' . substr($response_body, 0, 1000), array('source' => 'litho-wc'));
            }
            return new WP_Error('litho_api_error', __('Operacja API Litho nie powiodła się. Spróbuj ponownie.', 'litho-wc'), array('status' => $status));
        }
        $decoded = json_decode($response_body, true);
        return is_array($decoded) ? $decoded : array();
    }
}
