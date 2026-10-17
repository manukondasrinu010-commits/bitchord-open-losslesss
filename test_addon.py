import json
import unittest
from unittest.mock import patch
import server

class AddonContractTests(unittest.TestCase):
    def test_manifest(self):
        status, headers, body = server.handle_request("GET", "/manifest.json")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "dev.sunny.bitchord.open-lossless")
        self.assertEqual(data["checkValidLossless"], 0)
        self.assertIn("search", data["resources"])
        self.assertIn("stream", data["resources"])

    def test_health(self):
        status, _, body = server.handle_request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_empty_search(self):
        status, _, body = server.handle_request("GET", "/search", "q=")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"tracks": []})

    def test_unknown_endpoint(self):
        status, _, _ = server.handle_request("GET", "/does-not-exist")
        self.assertEqual(status, 404)

    def test_post_rejected(self):
        status, _, _ = server.handle_request("POST", "/manifest.json")
        self.assertEqual(status, 405)

    def test_track_token_round_trip(self):
        token = server._encode_track("public_item-123", "folder/song.flac")
        self.assertEqual(server._decode_track(token), ("public_item-123", "folder/song.flac"))

    def test_bad_track_token_rejected(self):
        status, _, body = server.handle_request("GET", "/stream/not-a-valid-token")
        self.assertEqual(status, 404)

    def test_search_results_filter_to_flac_and_license(self):
        mock_results = [
            {
                "id": "sample-id",
                "title": "Sample Song",
                "artist": "Sample Artist",
                "album": "Sample Album",
                "artworkURL": "https://archive.org/services/img/sample-id",
                "format": "flac",
                "audioQuality": "LOSSLESS"
            }
        ]
        with patch.object(server, "_archive_results", return_value=mock_results):
            status, _, body = server.handle_request("GET", "/search", "q=sample")
        self.assertEqual(status, 200)
        result = json.loads(body)["tracks"][0]
        self.assertEqual(result["format"], "flac")
        self.assertEqual(result["audioQuality"], "LOSSLESS")

if __name__ == "__main__":
    unittest.main()
