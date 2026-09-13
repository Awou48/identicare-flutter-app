import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

class AuthService with ChangeNotifier {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  AuthService() {
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
        'displayName': displayName.trim(),
        'phoneNumber': phoneNumber,
        'noBpjs': noBpjs?.trim() ?? '',
        'createdAt': FieldValue.serverTimestamp(),
      });
      notifyListeners();
      return null;
    } on FirebaseAuthException catch (e) {
      return e.message;
    }
  }

  Future<String?> signIn(
      {required String email, required String password}) async {
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
