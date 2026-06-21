package com.construction.rag.gateway;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

@Component
class ClientSecretCrypto {
  private static final SecureRandom RANDOM = new SecureRandom();
  private static final int GCM_TAG_BITS = 128;
  private static final int IV_BYTES = 12;
  private final GatewayProperties props;

  ClientSecretCrypto(GatewayProperties props) {
    this.props = props;
  }

  String apiKeyHash(String apiKey) {
    if (apiKey == null || apiKey.isBlank()) throw new IllegalArgumentException("api key is required");
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      return Base64.getEncoder().encodeToString(digest.digest(apiKey.getBytes(StandardCharsets.UTF_8)));
    } catch (GeneralSecurityException ex) {
      throw new IllegalStateException("api key hashing unavailable", ex);
    }
  }

  String encrypt(String plaintext) {
    if (plaintext == null) throw new IllegalArgumentException("plaintext is required");
    try {
      byte[] iv = new byte[IV_BYTES];
      RANDOM.nextBytes(iv);
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(GCM_TAG_BITS, iv));
      byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
      ByteBuffer buffer = ByteBuffer.allocate(iv.length + encrypted.length);
      buffer.put(iv);
      buffer.put(encrypted);
      return Base64.getEncoder().encodeToString(buffer.array());
    } catch (GeneralSecurityException ex) {
      throw new IllegalStateException("db password encryption failed", ex);
    }
  }

  String decrypt(String encrypted) {
    if (encrypted == null || encrypted.isBlank()) throw new IllegalArgumentException("encrypted db password is required");
    try {
      byte[] decoded = Base64.getDecoder().decode(encrypted);
      ByteBuffer buffer = ByteBuffer.wrap(decoded);
      byte[] iv = new byte[IV_BYTES];
      buffer.get(iv);
      byte[] ciphertext = new byte[buffer.remaining()];
      buffer.get(ciphertext);
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(GCM_TAG_BITS, iv));
      return new String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8);
    } catch (GeneralSecurityException | IllegalArgumentException ex) {
      throw new IllegalStateException("db password decryption failed", ex);
    }
  }

  private SecretKeySpec key() {
    String encoded = props.clientDbEncryptionKey();
    if (encoded == null || encoded.isBlank()) {
      throw new IllegalStateException("GATEWAY_CLIENT_DB_ENCRYPTION_KEY is required for API-key client DB credentials");
    }
    byte[] bytes = Base64.getDecoder().decode(encoded);
    if (bytes.length != 32) throw new IllegalStateException("GATEWAY_CLIENT_DB_ENCRYPTION_KEY must be 32 base64-encoded bytes");
    return new SecretKeySpec(bytes, "AES");
  }
}
