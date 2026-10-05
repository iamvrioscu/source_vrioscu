from ..time_utils import now_iso
from .base import like_escape, row, rows


PROFILE_FIELDS = (
    "first_name",
    "last_name",
    "country",
    "purpose",
)

SEARCH_SQL = (
    " WHERE u.username LIKE ? ESCAPE '\\'"
    " OR u.email LIKE ? ESCAPE '\\'"
    " OR u.first_name LIKE ? ESCAPE '\\'"
    " OR u.last_name LIKE ? ESCAPE '\\'"
)


class UserRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(
        self,
        *,
        username,
        email,
        password_hash,
        first_name="",
        last_name="",
        country="",
        purpose="",
        role="user",
    ):
        ts = now_iso()

        cur = self.conn.execute(
            """
            INSERT INTO users (
                username,
                email,
                password_hash,
                first_name,
                last_name,
                country,
                purpose,
                role,
                created_at,
                updated_at,
                password_changed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                email,
                password_hash,
                first_name,
                last_name,
                country,
                purpose,
                role,
                ts,
                ts,
                ts,
            ),
        )

        return cur.lastrowid

    def get(self, user_id):
        return row(
            self.conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        )

    def get_by_login(self, identifier):
        return row(
            self.conn.execute(
                """
                SELECT *
                FROM users
                WHERE email = ? OR username = ?
                LIMIT 1
                """,
                (identifier, identifier),
            ).fetchone()
        )

    def exists(
        self,
        *,
        username=None,
        email=None,
        exclude_id=None,
    ):
        clauses = []
        params = []

        if username:
            clauses.append("username = ?")
            params.append(username)

        if email:
            clauses.append("email = ?")
            params.append(email)

        if not clauses:
            return False

        sql = (
            "SELECT 1 FROM users WHERE "
            + " OR ".join(clauses)
        )

        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)

        return (
            self.conn.execute(sql, params).fetchone()
            is not None
        )

    def update_profile(self, user_id, **fields):
        allowed = {
            key: value
            for key, value in fields.items()
            if key in PROFILE_FIELDS + ("email",)
        }

        if not allowed:
            return

        sets = ", ".join(
            f"{key} = ?" for key in allowed
        )

        self.conn.execute(
            f"""
            UPDATE users
            SET {sets},
                updated_at = ?
            WHERE id = ?
            """,
            (
                *allowed.values(),
                now_iso(),
                user_id,
            ),
        )

    def set_password(self, user_id, password_hash):
        ts = now_iso()

        self.conn.execute(
            """
            UPDATE users
            SET password_hash = ?,
                password_changed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                password_hash,
                ts,
                ts,
                user_id,
            ),
        )

    def record_failure(
        self,
        user_id,
        max_failures,
        lock_until_iso,
    ):
        self.conn.execute(
            """
            UPDATE users
            SET failed_login_count =
                    failed_login_count + 1,
                locked_until =
                    CASE
                        WHEN failed_login_count + 1 >= ?
                        THEN ?
                        ELSE locked_until
                    END
            WHERE id = ?
            """,
            (
                max_failures,
                lock_until_iso,
                user_id,
            ),
        )

    def record_success(self, user_id):
        self.conn.execute(
            """
            UPDATE users
            SET failed_login_count = 0,
                locked_until = NULL,
                last_login_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                now_iso(),
                user_id,
            ),
        )

    def set_active(self, user_id, active: bool):
        self.conn.execute(
            """
            UPDATE users
            SET is_active = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                1 if active else 0,
                now_iso(),
                user_id,
            ),
        )

    def set_role(self, user_id, role):
        self.conn.execute(
            """
            UPDATE users
            SET role = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                role,
                now_iso(),
                user_id,
            ),
        )

    def delete(self, user_id):
        self.conn.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )

    def list(
        self,
        *,
        search="",
        limit=50,
        offset=0,
    ):
        params = []

        sql = (
            "SELECT "
            "u.id, "
            "u.username, "
            "u.email, "
            "u.first_name, "
            "u.last_name, "
            "u.country, "
            "u.purpose, "
            "u.role, "
            "u.is_active, "
            "u.created_at, "
            "u.last_login_at, "
            "COALESCE(p.opted_in, 0) AS opted_in "
            "FROM users u "
            "LEFT JOIN product_update_preferences p "
            "ON p.user_id = u.id"
        )

        if search:
            sql += SEARCH_SQL

            search_pattern = f"%{like_escape(search)}%"

            params.extend(
                [search_pattern] * 4
            )

        sql += (
            " ORDER BY u.created_at DESC, "
            "u.id DESC "
            "LIMIT ? OFFSET ?"
        )

        params.extend(
            [limit, offset]
        )

        return rows(
            self.conn.execute(
                sql,
                params,
            ).fetchall()
        )

    def count(self, search=""):
        if not search:
            return self.conn.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]

        search_pattern = f"%{like_escape(search)}%"

        sql = (
            "SELECT COUNT(*) "
            "FROM users u"
            + SEARCH_SQL
        )

        return self.conn.execute(
            sql,
            [search_pattern] * 4,
        ).fetchone()[0]

    def count_admins(self):
        return self.conn.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE role = 'admin'
              AND is_active = 1
            """
        ).fetchone()[0]