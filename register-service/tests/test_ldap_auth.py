import unittest
from pathlib import Path

import ldap3

from regsvc.ldap_auth import LdapAuthenticator, LdapUnavailable, build_user_dn

CA = str(Path(__file__).resolve().parent.parent / "ldap-ca.crt")
DN = "uid=will,ou=people,dc=mirrorborn,dc=us"


class FakeConn:
    def __init__(self, who=None):
        self.bound = True
        self._who = who
        self.unbound = False
        outer = self

        class Std:
            def who_am_i(self):
                return outer._who

        class Ext:
            standard = Std()

        self.extend = Ext()

    def unbind(self):
        self.unbound = True


def factory_returning(conn):
    def make(server, user_dn, password):
        make.called_with = (user_dn, password)
        return conn
    return make


def factory_raising(exc):
    def make(server, user_dn, password):
        raise exc
    return make


class TestBuildUserDn(unittest.TestCase):
    def test_normal_uid(self):
        self.assertEqual(build_user_dn("will"), DN)

    def test_injection_attempts_rejected(self):
        for bad in ["will,ou=groups", "wi ll", "will*", "../will", "",
                    "will)", "w(i)ll", "üser", "-leading-dash"]:
            self.assertIsNone(build_user_dn(bad), bad)


class TestAuthenticate(unittest.TestCase):
    def auth(self, factory):
        return LdapAuthenticator("aletheia-core.pizzly-halfmoon.ts.net",
                                 CA, connection_factory=factory)

    def test_success(self):
        conn = FakeConn(who=f"dn:{DN}")
        result = self.auth(factory_returning(conn)).authenticate(
            "will", "correct-horse")
        self.assertEqual(result, "will")
        self.assertTrue(conn.unbound)

    def test_invalid_credentials_fail_closed(self):
        exc = ldap3.core.exceptions.LDAPBindError("invalid credentials")
        result = self.auth(factory_raising(exc)).authenticate(
            "will", "wrong")
        self.assertIsNone(result)

    def test_unreachable_raises_unavailable(self):
        exc = ldap3.core.exceptions.LDAPSocketOpenError("cannot connect")
        with self.assertRaises(LdapUnavailable):
            self.auth(factory_raising(exc)).authenticate("will", "pw")

    def test_generic_transport_error_raises_unavailable(self):
        with self.assertRaises(LdapUnavailable):
            self.auth(factory_raising(OSError("boom"))).authenticate(
                "will", "pw")

    def test_empty_password_never_touches_network(self):
        called = []

        def make(server, user_dn, password):
            called.append(True)
            return FakeConn(who=f"dn:{DN}")

        result = self.auth(make).authenticate("will", "")
        self.assertIsNone(result)
        self.assertEqual(called, [])

    def test_bad_uid_never_touches_network(self):
        called = []

        def make(server, user_dn, password):
            called.append(True)
            return FakeConn()

        result = self.auth(make).authenticate("will,ou=groups", "pw")
        self.assertIsNone(result)
        self.assertEqual(called, [])

    def test_whoami_mismatch_rejected(self):
        conn = FakeConn(who="dn:uid=mallory,ou=people,dc=mirrorborn,dc=us")
        result = self.auth(factory_returning(conn)).authenticate(
            "will", "pw")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
