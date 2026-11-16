"""LDAP password authentication against the house OpenLDAP directory.

Layout (~/workspace/ldap-integration/): base dc=mirrorborn,dc=us,
people under ou=people — a user's DN is
``uid=<uid>,ou=people,dc=mirrorborn,dc=us``.

The service authenticates by a SIMPLE BIND AS THE LOGGING-IN USER with
the password they presented. No service account, no directory writes.
Every failure mode fails closed:

- malformed uid (anything that could escape the DN template) -> reject
  before any network traffic;
- empty password -> reject (an empty-password LDAP bind is an
  *unauthenticated* bind and can report success — the classic trap);
- invalid credentials -> reject;
- directory unreachable / TLS failure / any other LDAP error ->
  LdapUnavailable, which the app turns into a 503, never a session.
"""

import re
import ssl

UID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
USER_DN_TEMPLATE = "uid={uid},ou=people,dc=mirrorborn,dc=us"


class LdapUnavailable(Exception):
    """The directory could not be reached or did not answer cleanly."""


def build_user_dn(uid):
    """DN for a uid, or None if the uid is not safe to interpolate."""
    if not uid or not UID_RE.match(uid):
        return None
    return USER_DN_TEMPLATE.format(uid=uid)


def _default_connection_factory(server, user_dn, password):
    import ldap3

    conn = ldap3.Connection(
        server,
        user=user_dn,
        password=password,
        auto_bind=True,
        raise_exceptions=True,
        receive_timeout=10,
    )
    return conn


class LdapAuthenticator:
    def __init__(self, host, ca_cert_file, port=636,
                 connection_factory=None):
        self.host = host
        self.port = port
        self.ca_cert_file = ca_cert_file
        self._factory = connection_factory or _default_connection_factory

    def _server(self):
        import ldap3

        tls = ldap3.Tls(validate=ssl.CERT_REQUIRED,
                        ca_certs_file=self.ca_cert_file)
        return ldap3.Server(self.host, port=self.port, use_ssl=True,
                            tls=tls, get_info=ldap3.NONE,
                            connect_timeout=5)

    def authenticate(self, uid, password):
        """Return the uid on a successful bind, None on bad credentials.

        Raises LdapUnavailable for transport/TLS/unexpected errors.
        """
        dn = build_user_dn(uid)
        if dn is None:
            return None
        if not password:
            return None
        import ldap3

        try:
            conn = self._factory(self._server(), dn, password)
        except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
            # raise_exceptions=True surfaces a refused bind (result 49)
            # as this exception, not as LDAPBindError. A refusal is a
            # normal "bad credentials" outcome, not an outage.
            return None
        except ldap3.core.exceptions.LDAPBindError:
            return None
        except Exception as exc:  # socket, TLS, timeout, protocol...
            raise LdapUnavailable(str(exc)) from exc
        try:
            # A bound connection whose bind was *unauthenticated* (empty
            # password handled above, but belt and braces) must not pass:
            # require the connection to report our DN as its identity.
            if not conn.bound:
                return None
            who = conn.extend.standard.who_am_i()
            if who is not None and who != f"dn:{dn}":
                return None
            return uid
        except Exception as exc:
            raise LdapUnavailable(str(exc)) from exc
        finally:
            try:
                conn.unbind()
            except Exception:
                pass
