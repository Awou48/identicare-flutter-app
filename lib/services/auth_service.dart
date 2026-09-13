import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

/// Autentikasi Firebase.
///
/// Keputusan database hibrida: Firebase Auth tetap menjadi penyedia identitas
/// dan Firestore tetap menyimpan `riwayat_konsultasi`, sementara seluruh data
/// BPJS, template biometrik, dan log verifikasi ada di MongoDB di belakang API
/// Python. `firebase_uid` adalah satu-satunya jahitan antara keduanya.
class AuthService with ChangeNotifier {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  AuthService() {
    // Sebelumnya kelas ini meng-extend ChangeNotifier tetapi tidak pernah
    // memberi notifikasi, sehingga Provider hanya berfungsi sebagai service
    // locator dan perubahan status login tidak pernah dipropagasi.
    _auth.authStateChanges().listen((_) => notifyListeners());
  }

  Stream<User?> get authStateChanges => _auth.authStateChanges();
  User? get currentUser => _auth.currentUser;
  bool get isSignedIn => _auth.currentUser != null;

  Stream<DocumentSnapshot> get userProfileStream {
    if (currentUser == null) {
      return const Stream.empty();
    }
    return _firestore.collection('users').doc(currentUser!.uid).snapshots();
  }

  /// Token ID untuk dikirim ke backend Python sebagai `Authorization: Bearer`.
  ///
  /// Token Firebase berumur satu jam; SDK menyegarkannya sendiri, jadi ini aman
  /// dipanggil sebelum setiap permintaan.
  Future<String?> getIdToken({bool forceRefresh = false}) async {
    final user = _auth.currentUser;
    if (user == null) return null;
    try {
      return await user.getIdToken(forceRefresh);
    } on FirebaseAuthException catch (e) {
      debugPrint('getIdToken gagal: ${e.code}');
      return null;
    }
  }

  Future<String?> signUp({
    required String email,
    required String password,
    required String displayName,
    String? noBpjs,
    String phoneNumber = '',
  }) async {
    try {
      final userCredential = await _auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );

      await _firestore.collection('users').doc(userCredential.user!.uid).set({
        'email': email,
        // Dulu di sini tertulis 'Marcel Sebastian' untuk SETIAP akun baru.
        // Identitas adalah inti produk ini; nama tidak boleh dikarang.
        'displayName': displayName.trim(),
        'phoneNumber': phoneNumber,
        // Menautkan akun ke peserta BPJS di MongoDB. Tanpa ini, riwayat
        // verifikasi tidak dapat dicari untuk pengguna ini.
        'noBpjs': noBpjs?.trim() ?? '',
        'createdAt': FieldValue.serverTimestamp(),
      });
      notifyListeners();
      return null;
    } on FirebaseAuthException catch (e) {
      return e.message;
    }
  }

  Future<String?> signIn({required String email, required String password}) async {
    try {
      await _auth.signInWithEmailAndPassword(email: email, password: password);
      notifyListeners();
      return null;
    } on FirebaseAuthException catch (e) {
      return e.message;
    }
  }

  Future<void> signOut() async {
    await _auth.signOut();
    notifyListeners();
  }

  /// Buat dokumen profil untuk akun yang tidak memilikinya.
  ///
  /// Ini terjadi kalau akun dibuat di luar alur pendaftaran aplikasi, atau
  /// penulisan Firestore-nya gagal saat mendaftar. Halaman profil dulu hanya
  /// berkata "Silakan coba login ulang" - yang tidak menolong, karena login
  /// ulang tidak membuat dokumen. Sekarang profil dibuat dari data akun
  /// Firebase Auth. displayName memakai bagian lokal email sebagai cadangan,
  /// karena aturan Firestore menolak displayName kosong.
  Future<bool> ensureProfileDocument() async {
    final user = _auth.currentUser;
    if (user == null) return false;
    final ref = _firestore.collection('users').doc(user.uid);
    try {
      final snap = await ref.get();
      if (snap.exists) return true;
      final email = user.email ?? '';
      final fallbackName =
          email.contains('@') ? email.split('@').first : 'Pengguna';
      await ref.set({
        'email': email,
        'displayName': (user.displayName ?? '').trim().isNotEmpty
            ? user.displayName!.trim()
            : fallbackName,
        'phoneNumber': user.phoneNumber ?? '',
        'noBpjs': '',
        'createdAt': FieldValue.serverTimestamp(),
      });
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('ensureProfileDocument gagal: $e');
      return false;
    }
  }

  /// Nomor BPJS pengguna, dibutuhkan untuk memulai sesi verifikasi.
  Future<String?> getNoBpjs() async {
    final user = _auth.currentUser;
    if (user == null) return null;
    final doc = await _firestore.collection('users').doc(user.uid).get();
    final value = doc.data()?['noBpjs'] as String?;
    return (value == null || value.isEmpty) ? null : value;
  }

  Future<void> setNoBpjs(String noBpjs) async {
    final user = _auth.currentUser;
    if (user == null) return;
    await _firestore
        .collection('users')
        .doc(user.uid)
        .set({'noBpjs': noBpjs.trim()}, SetOptions(merge: true));
    notifyListeners();
  }
}
