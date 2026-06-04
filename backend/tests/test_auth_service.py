from app.services.auth_service import AuthService


def test_access_token_round_trip():
    token = AuthService.create_access_token(
        user_id="user-1",
        email="user@example.com",
        role="user",
    )

    payload = AuthService.verify_token(token)

    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "user"


def test_password_hash_round_trip():
    hashed = AuthService.hash_password("strong-password")

    assert hashed != "strong-password"
    assert AuthService.verify_password("strong-password", hashed)
    assert not AuthService.verify_password("wrong-password", hashed)
