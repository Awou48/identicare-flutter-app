import 'package:flutter_test/flutter_test.dart';
import 'package:identicare_mobile/models/api_result.dart';
import 'package:identicare_mobile/models/review_data.dart';
import 'package:identicare_mobile/models/step_results.dart';
import 'package:identicare_mobile/models/verification_history.dart';
import 'package:identicare_mobile/models/verification_session.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';

void main() {
  group('SessionStep', () {
    test('urutan langkah sesuai state machine server', () {
      expect(SessionStep.values.map((s) => s.wire).toList(),
          ['face', 'fingerprint', 'review', 'commit']);
      expect(SessionStep.face.index0, 0);
      expect(SessionStep.commit.index0, 3);
    });

    test('fromWire memetakan nilai yang dikenal dan menolak sisanya', () {
      expect(SessionStep.fromWire('fingerprint'), SessionStep.fingerprint);
      expect(SessionStep.fromWire('tidak_ada'), isNull);
      expect(SessionStep.fromWire(null), isNull);
    });

    test('label ditampilkan dalam Bahasa Indonesia', () {
      expect(SessionStep.face.label, 'Scan Wajah');
      expect(SessionStep.fingerprint.label, 'Scan Sidik Jari');
      expect(SessionStep.review.label, 'Periksa Ulang Data');
      expect(SessionStep.commit.label, 'Verifikasi Data');
    });
  });

  group('SessionStatus', () {
    test('status terminal dikenali', () {
      for (final status in [
        SessionStatus.committed,
        SessionStatus.rejected,
        SessionStatus.expired,
        SessionStatus.cancelled,
      ]) {
        expect(status.isTerminal, isTrue,
            reason: '$status seharusnya terminal');
      }
      for (final status in [
        SessionStatus.created,
        SessionStatus.facePassed,
        SessionStatus.fingerprintPassed,
        SessionStatus.reviewed,
      ]) {
        expect(status.isTerminal, isFalse);
      }
    });

    test('fromWire membaca snake_case dari server', () {
      expect(SessionStatus.fromWire('face_passed'), SessionStatus.facePassed);
      expect(SessionStatus.fromWire('fingerprint_passed'),
          SessionStatus.fingerprintPassed);
    });
  });

  group('FaceStepResult', () {
    test('kegagalan datang sebagai HTTP 200 dan tetap membawa skor', () {
      final result = FaceStepResult.fromJson({
        'status': 'ok',
        'step': 'face',
        'result': 'failed',
        'error_code': 'FACE_MISMATCH',
        'message': 'Wajah tidak cocok dengan data peserta. Sisa percobaan: 2.',
        'match_score': 0.21,
        'threshold': 0.42,
        'attempts_used': 1,
        'attempts_left': 2,
      });

      expect(result.passed, isFalse);
      expect(result.errorCode, 'FACE_MISMATCH');
      expect(result.matchScore, 0.21);
      expect(result.attemptsLeft, 2);
      expect(result.isExhausted, isFalse);
    });

    test('batas percobaan habis dikenali', () {
      expect(
        FaceStepResult.fromJson(
            {'result': 'failed', 'error_code': 'MAX_ATTEMPTS'}).isExhausted,
        isTrue,
      );
      expect(
        FaceStepResult.fromJson({'result': 'failed', 'attempts_left': 0})
            .isExhausted,
        isTrue,
      );
    });

    test('keberhasilan membawa nonce baru untuk langkah sidik jari', () {
      final result = FaceStepResult.fromJson({
        'result': 'passed',
        'match_score': 0.514,
        'nonce': 'a7f2abc',
        'liveness': {
          'passed': true,
          'score': 0.88,
          'method': 'active_challenge_v1'
        },
      });
      expect(result.passed, isTrue);
      expect(result.nonce, 'a7f2abc');
      expect(result.liveness!.score, 0.88);
    });
  });

  group('FingerprintStepResult', () {
    test('SOFTWARE tidak dianggap terikat perangkat keras', () {
      final soft = FingerprintStepResult.fromJson(
          {'result': 'passed', 'security_level': 'SOFTWARE'});
      expect(soft.passed, isTrue);
      expect(soft.isHardwareBacked, isFalse);
    });

    test('TEE dan STRONGBOX dianggap terikat perangkat keras', () {
      for (final level in ['TEE', 'STRONGBOX']) {
        expect(
          FingerprintStepResult.fromJson(
              {'result': 'passed', 'security_level': level}).isHardwareBacked,
          isTrue,
        );
      }
    });
  });

  group('CommitResult', () {
    test('keputusan dan sinyal fraud diurai', () {
      final result = CommitResult.fromJson({
        'decision': 'REVIEW',
        'receipt_no': 'VRF-20260908-000123',
        'decided_at': '2026-09-08T07:36:44Z',
        'risk': {
          'score': 45,
          'band': 'MEDIUM',
          'signals': [
            {
              'rule_id': 'SHARED_DEVICE',
              'severity': 'medium',
              'weight': 20,
              'title': 'Satu perangkat dipakai banyak peserta',
            }
          ],
        },
        'summary': {'wajah': 0.51},
      });

      expect(result.needsReview, isTrue);
      expect(result.isApproved, isFalse);
      expect(result.riskScore, 45);
      expect(result.signals.single.ruleId, 'SHARED_DEVICE');
      expect(result.signals.single.isCritical, isFalse);
    });

    test('sinyal critical ditandai', () {
      final result = CommitResult.fromJson({
        'decision': 'REJECTED',
        'decided_at': '2026-09-08T07:36:44Z',
        'risk': {
          'score': 40,
          'band': 'HIGH',
          'signals': [
            {
              'rule_id': 'SIMULTANEOUS_CLAIM',
              'severity': 'critical',
              'weight': 40
            }
          ],
        },
      });
      expect(result.isRejected, isTrue);
      expect(result.signals.single.isCritical, isTrue);
      expect(result.receiptNo, isNull);
    });
  });

  group('Payload kanonik sidik jari', () {
    test('sama persis dengan yang dibentuk server', () {
      final payload = VerificationConstants.canonicalPayload(
        sessionId: 's1',
        nonce: 'n1',
        deviceUid: 'd1',
        noBpjs: '0001234567890',
        timestamp: 1757000000,
      );
      expect(payload, 'identicare-v1|s1|n1|d1|0001234567890|1757000000');
    });

    test('setiap field terikat ke dalam tanda tangan', () {
      String build({
        String sessionId = 's1',
        String nonce = 'n1',
        String deviceUid = 'd1',
        String noBpjs = '0001234567890',
        int timestamp = 1757000000,
      }) =>
          VerificationConstants.canonicalPayload(
            sessionId: sessionId,
            nonce: nonce,
            deviceUid: deviceUid,
            noBpjs: noBpjs,
            timestamp: timestamp,
          );

      final base = build();

      expect(build(sessionId: 'lain'), isNot(base));
      expect(build(nonce: 'lain'), isNot(base));
      expect(build(deviceUid: 'lain'), isNot(base));
      expect(build(noBpjs: '9999999999999'), isNot(base));
      expect(build(timestamp: 1757000001), isNot(base));
    });
  });

  group('ApiResult', () {
    test('Ok membawa nilainya', () {
      const result = Ok<int>(42);
      expect(result.isOk, isTrue);
      expect(result.valueOrNull, 42);
      expect(result.when(ok: (v) => v * 2, failure: (_) => -1), 84);
    });

    test('ApiFailure mengenali sesi yang sudah tidak berlaku', () {
      for (final code in [
        'SESSION_EXPIRED',
        'SESSION_NOT_FOUND',
        'SESSION_CLOSED'
      ]) {
        expect(
          ApiFailure<void>(errorCode: code, message: '').isSessionGone,
          isTrue,
          reason: code,
        );
      }
      expect(
        const ApiFailure<void>(errorCode: 'FACE_MISMATCH', message: '')
            .isSessionGone,
        isFalse,
      );
    });

    test('kegagalan jaringan dibedakan dari error server', () {
      expect(
        const ApiFailure<void>(errorCode: 'NETWORK_ERROR', message: '')
            .isNetworkError,
        isTrue,
      );
    });
  });

  group('VerificationHistoryEntry', () {
    test('tanggal, metode, status dan lokasi diurai', () {
      final entry = VerificationHistoryEntry.fromJson({
        'session_id': '66df',
        'receipt_no': 'VRF-20260908-000123',
        'tanggal': '2026-09-08T07:36:44Z',
        'metode': ['wajah', 'sidik_jari'],
        'status': 'APPROVED',
        'lokasi': {'faskes': 'RS Harapan Kita', 'kode_faskes': '0110R001'},
        'skor': {'wajah': 0.514, 'liveness': 0.88},
        'risk_band': 'LOW',
      });

      expect(entry.metodeLabel, 'Wajah + Sidik Jari');
      expect(entry.statusLabel, 'Disetujui');
      expect(entry.faskes, 'RS Harapan Kita');
      expect(entry.skorWajah, 0.514);
    });
  });

  group('PesertaFull', () {
    test('NIK tetap bertopeng walaupun kedua faktor sudah lolos', () {
      final peserta = PesertaFull.fromJson({
        'nama_lengkap': 'Marcel Iliantino',
        'no_bpjs': '0001234567890',
        'nik_masked': '3174********0001',
        'status_kepesertaan': 'AKTIF',
        'jenis_kelamin': 'L',
      });
      expect(peserta.nikMasked, contains('*'));
      expect(peserta.isAktif, isTrue);
      expect(peserta.jenisKelaminLabel, 'Laki-laki');
    });
  });
}
