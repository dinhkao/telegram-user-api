import unittest

from server_app.cloudinary_routes import _camera_image, _decode_cursor, _delivery_variant, _encode_cursor, _search_expression


class CloudinaryRoutesTest(unittest.TestCase):
    def test_delivery_variant_keeps_credentials_out_and_adds_transform(self):
        url = "https://res.cloudinary.com/demo/image/upload/v1/camera_2026/a.jpg"
        self.assertEqual(
            _delivery_variant(url, "f_auto,q_auto,w_640"),
            "https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,w_640/v1/camera_2026/a.jpg",
        )

    def test_camera_image_exposes_only_safe_gallery_fields(self):
        image = _camera_image({
            "asset_id": "asset-1",
            "public_id": "camera_2026/cam-01",
            "resource_type": "image",
            "type": "upload",
            "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/camera_2026/cam-01.jpg",
            "width": 1920,
            "height": 1080,
            "bytes": 12345,
            "created_at": "2026-07-13T07:00:00Z",
            "api_key": "must-not-leak",
        })
        self.assertEqual(image["id"], "main:asset-1")
        self.assertEqual(image["name"], "cam-01")
        self.assertNotIn("api_key", image)
        self.assertIn("q_auto:low", image["thumbnail_url"])
        self.assertIn("w_320", image["thumbnail_url"])
        self.assertNotIn("g_auto", image["thumbnail_url"])
        self.assertIn("c_limit", image["preview_url"])

    def test_non_image_asset_is_ignored(self):
        self.assertIsNone(_camera_image({"resource_type": "video", "type": "upload"}))

    def test_multi_account_cursor_round_trip(self):
        state = {"main": "cursor-one", "camera_2": None}
        encoded = _encode_cursor(state)
        self.assertIsNotNone(encoded)
        self.assertEqual(_decode_cursor(encoded), state)
        self.assertNotIn("cursor-one", encoded)

    def test_searches_both_camera_subfolders(self):
        expression = _search_expression({"folder": "camera_2026"}, None, "folder")
        self.assertIn('folder="camera_2026/channel_11"', expression)
        self.assertIn('folder="camera_2026/channel_14"', expression)
        self.assertIn("resource_type:image", expression)


if __name__ == "__main__":
    unittest.main()
