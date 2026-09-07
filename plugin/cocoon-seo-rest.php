<?php
/**
 * Plugin Name: Cocoon SEO REST API
 * Description: CocoonテーマのSEOメタフィールドをWordPress REST APIで読み書きできるようにする
 * Version: 1.0
 * Author: AIのトリセツ
 */

add_action('init', function () {
    $fields = [
        '_cf_meta_title'       => 'string',
        '_cf_meta_description' => 'string',
        '_cf_meta_keywords'    => 'string',
    ];

    foreach ($fields as $key => $type) {
        register_post_meta('post', $key, [
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => $type,
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ]);
    }
});
