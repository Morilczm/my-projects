from datetime import datetime, timedelta


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_logout_and_password_hashing(app_module, client):
    good = client.post("/api/auth/login", json={
        "email": "student.test@lexibridge.local",
        "password": "Student1234",
    })
    assert good.status_code == 200
    token = good.get_json()["token"]

    bad = client.post("/api/auth/login", json={
        "email": "student.test@lexibridge.local",
        "password": "WrongPassword",
    })
    assert bad.status_code == 401
    assert bad.get_json()["error_code"] == "AUTH_REQUIRED"

    me = client.get("/api/auth/me", headers=bearer(token))
    assert me.status_code == 200

    logout = client.post("/api/auth/logout", headers=bearer(token))
    assert logout.status_code == 200
    after_logout = client.get("/api/auth/me", headers=bearer(token))
    assert after_logout.status_code == 401

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        assert user.password_hash != "Student1234"
        assert user.password_hash.startswith("pbkdf2:")


def test_missing_and_expired_token_return_401(app_module, client):
    missing = client.get("/api/terminology/cards")
    assert missing.status_code == 401
    assert missing.get_json()["error_code"] == "AUTH_REQUIRED"

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        token_value = "expired-test-token"
        token = app_module.AuthToken(
            user_id=user.id,
            token=token_value,
            token_hash=app_module.token_hash(token_value),
            created_at=app_module.current_time_text(),
            expires_at=(datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
            revoked=False,
        )
        app_module.db.session.add(token)
        app_module.db.session.commit()

    expired = client.get("/api/auth/me", headers=bearer("expired-test-token"))
    assert expired.status_code == 401
    assert expired.get_json()["error_code"] == "TOKEN_EXPIRED"


def test_token_redaction_in_system_logs(app_module):
    fake_key = "sk-" + "testredactionplaceholder000000000000"
    raw = f"Bearer abcdefghijklmnopqrstuvwxyz123456 token=abcdefghijklmnopqrstuvwxyz123456 {fake_key}"
    redacted = app_module.redact_for_log(raw)
    assert "abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert fake_key not in redacted
    assert "REDACTED" in redacted
