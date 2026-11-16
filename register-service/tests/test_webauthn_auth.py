import unittest

from regsvc.webauthn_auth import WebAuthnCeremonies, WebAuthnError

CER = WebAuthnCeremonies("register.phext.io", "https://register.phext.io")


class TestOptions(unittest.TestCase):
    def test_registration_options_shape(self):
        challenge, options_json = CER.registration_options("will", [])
        self.assertIsInstance(challenge, bytes)
        self.assertIn('"challenge"', options_json)
        self.assertIn("register.phext.io", options_json)

    def test_authentication_options_shape(self):
        creds = [{"credential_id": "AAEC", "public_key": "pk",
                  "sign_count": 0, "transports": ["internal"]}]
        challenge, options_json = CER.authentication_options(creds)
        self.assertIsInstance(challenge, bytes)
        self.assertIn('"allowCredentials"', options_json)


class TestVerifyFailsClosed(unittest.TestCase):
    def test_registration_garbage_credential_raises(self):
        with self.assertRaises(WebAuthnError):
            CER.verify_registration({"id": "x", "rawId": "x",
                                     "response": {}, "type": "public-key"},
                                    b"some-challenge")

    def test_authentication_garbage_credential_raises(self):
        stored = {"credential_id": "AAEC", "public_key": "AAEC",
                  "sign_count": 0}
        with self.assertRaises(WebAuthnError):
            CER.verify_authentication(
                {"id": "AAEC", "rawId": "AAEC", "response": {},
                 "type": "public-key"},
                b"some-challenge", stored)


if __name__ == "__main__":
    unittest.main()
