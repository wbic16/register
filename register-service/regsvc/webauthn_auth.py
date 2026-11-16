"""WebAuthn (passkey) ceremonies via the `webauthn` library.

RP id: register.phext.io; expected origin: https://register.phext.io.
All verification failures raise WebAuthnError — callers fail closed.
The class wraps the library so tests can substitute a fake.
"""

import webauthn
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


def _transports(raw):
    """Stored transports are browser strings; the library wants enums."""
    out = []
    for t in raw or []:
        try:
            out.append(AuthenticatorTransport(t))
        except ValueError:
            continue
    return out

RP_NAME = "Waiting-on-Will Register"


class WebAuthnError(Exception):
    pass


def b64url(data: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url

    return bytes_to_base64url(data)


class WebAuthnCeremonies:
    def __init__(self, rp_id, origin):
        self.rp_id = rp_id
        self.origin = origin

    # -- registration -------------------------------------------------
    def registration_options(self, uid, existing_credentials):
        exclude = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(c["credential_id"]))
            for c in existing_credentials
        ]
        options = webauthn.generate_registration_options(
            rp_id=self.rp_id,
            rp_name=RP_NAME,
            user_id=uid.encode("utf-8"),
            user_name=uid,
            user_display_name=uid,
            exclude_credentials=exclude,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        return options.challenge, webauthn.options_to_json(options)

    def verify_registration(self, credential_json, expected_challenge):
        try:
            verified = webauthn.verify_registration_response(
                credential=credential_json,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
            )
        except Exception as exc:
            raise WebAuthnError(str(exc)) from exc
        return {
            "credential_id": b64url(verified.credential_id),
            "public_key": b64url(verified.credential_public_key),
            "sign_count": verified.sign_count,
        }

    # -- authentication ------------------------------------------------
    def authentication_options(self, credentials):
        allow = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(c["credential_id"]),
                transports=_transports(c.get("transports")),
            )
            for c in credentials
        ]
        options = webauthn.generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=allow,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        return options.challenge, webauthn.options_to_json(options)

    def verify_authentication(self, credential_json, expected_challenge,
                              credential):
        """Returns the new sign count; raises WebAuthnError on failure."""
        try:
            verified = webauthn.verify_authentication_response(
                credential=credential_json,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                credential_public_key=base64url_to_bytes(
                    credential["public_key"]),
                credential_current_sign_count=credential["sign_count"],
            )
        except Exception as exc:
            raise WebAuthnError(str(exc)) from exc
        # The responding credential must be the one we looked up.
        if b64url(verified.credential_id) != credential["credential_id"]:
            raise WebAuthnError("credential id mismatch")
        return verified.new_sign_count
