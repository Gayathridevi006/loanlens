from backend.security import EncryptedJSON, EncryptedText, create_access_token, decode_access_token, hash_password, verify_password


def test_encrypted_json_is_not_plaintext():
    codec = EncryptedJSON()
    value = {"pan": "ABCDE1234F", "income": 800000}
    encrypted = codec.process_bind_param(value, None)
    assert "ABCDE1234F" not in encrypted
    assert codec.process_result_value(encrypted, None) == value


def test_extracted_document_text_is_encrypted():
    codec = EncryptedText()
    encrypted = codec.process_bind_param("account 123456 and PAN ABCDE1234F", None)
    assert "ABCDE1234F" not in encrypted
    assert codec.process_result_value(encrypted, None).startswith("account 123456")


def test_scrypt_password_and_signed_access_token():
    encoded = hash_password("a-long-production-password")
    assert "a-long-production-password" not in encoded
    assert verify_password("a-long-production-password", encoded)
    assert not verify_password("wrong-password", encoded)
    claims = decode_access_token(create_access_token("officer-1", "loan_officer"))
    assert claims["sub"] == "officer-1"
    assert claims["role"] == "loan_officer"
