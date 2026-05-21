from app.core.security import hash_password, verify_password


def test_password_hash_and_verify_supports_long_passwords() -> None:
    password = "x" * 120
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True

