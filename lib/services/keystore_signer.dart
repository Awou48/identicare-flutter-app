import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class KeystoreSigner {
  static const _channel = MethodChannel('identicare/keystore');

  bool get isSupported {
    if (kIsWeb) return false;
    try {
      return Platform.isAndroid;
    } catch (_) {
      return false;
    }
  }

  Future<bool> hasKey(String alias) async {
    return await _invoke<bool>('hasKey', {'alias': alias}) ?? false;
  }

  Future<GeneratedKey> generateKey(String alias,
      {required List<int> challenge}) async {
    final map = await _invoke<Map>('generateKey', {
      'alias': alias,
      'challengeB64': base64Encode(challenge),
    });
    return GeneratedKey(
      publicKeyDerB64: map!['publicKeyDerB64'] as String,
      attestationChainB64:
          (map['attestationChainB64'] as List?)?.cast<String>() ?? const [],
      securityLevel: map['securityLevel'] as String? ?? 'UNKNOWN',
    );
  }

  Future<GeneratedKey?> getKey(String alias) async {
    final map = await _invoke<Map>('getKey', {'alias': alias});
    if (map == null) return null;
    return GeneratedKey(
      publicKeyDerB64: map['publicKeyDerB64'] as String,
      attestationChainB64:
          (map['attestationChainB64'] as List?)?.cast<String>() ?? const [],
      securityLevel: map['securityLevel'] as String? ?? 'UNKNOWN',
    );
  }

  Future<void> deleteKey(String alias) =>
      _invoke<bool>('deleteKey', {'alias': alias});

  Future<String> sign(
    String alias,
    String payload, {
    required String title,
    String subtitle = '',
    String negativeButton = 'Batal',
  }) async {
    final map = await _invoke<Map>('sign', {
      'alias': alias,
      'payload': payload,
      'title': title,
      'subtitle': subtitle,
      'negativeButton': negativeButton,
    });
    return map!['signatureB64'] as String;
  }

  Future<T?> _invoke<T>(String method, Map<String, Object?> args) async {
    try {
      return await _channel.invokeMethod<T>(method, args);
    } on PlatformException catch (e) {
      throw KeystoreException(e.code, e.message);
    } on MissingPluginException {
      throw const KeystoreException(
          'UNSUPPORTED', 'saluran keystore tidak tersedia');
    }
  }
}

class GeneratedKey {
  const GeneratedKey({
    required this.publicKeyDerB64,
    required this.attestationChainB64,
    required this.securityLevel,
  });

  final String publicKeyDerB64;
  final List<String> attestationChainB64;
  final String securityLevel;
}

class KeystoreException implements Exception {
  const KeystoreException(this.code, this.message);

  final String code;
  final String? message;

  bool get isStructural =>
      code == 'UNSUPPORTED' || code == 'HW_UNAVAILABLE' || code == 'ERROR';

  @override
  String toString() => 'KeystoreException($code, $message)';
}
